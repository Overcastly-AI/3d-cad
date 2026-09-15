"""The generated operation table must agree with the committed contract.

``just gen-check`` already diffs the generated file in CI. This is the cheaper,
closer guard that runs in every ``just test``, plus the checks a diff cannot
make: that the model NAMES the table carries actually resolve to components,
and that the table is not empty (a walk that finds nothing makes every "all of
them are fine" assertion vacuously true — the repo's own recurring defect
class).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from loft import _operations as operations_module
from loft._operation import Operation
from loft._operations import OPERATIONS

#: The table keyed by MODULE CONSTANT name (``DELETE_PARTS_…``) rather than
#: by operationId, because a call site names the constant. Built from the
#: module rather than hand-listed so it cannot drift from the generated file.
OPERATIONS_BY_CONSTANT: dict[str, Operation] = {
    name: value
    for name, value in vars(operations_module).items()
    if isinstance(value, Operation)
}

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


# ---------------------------------------------------------------------------
# CALL-SITE parity — the half `transport.py` documented and nobody had written
# ---------------------------------------------------------------------------
#
# ``Transport.call``'s docstring says "the contract-parity test closes the loop
# by asserting the two agree for every call site", and until 2026-09-15 no test
# in this file looked at a call site at all. The cost of that gap was not
# theoretical: ``Part.delete_feature`` omitted a REQUIRED query parameter and
# 422'd on every call, for every input, and the generated field that would have
# caught it (``Operation.required_query``) was read by nothing.
#
# So this walks the library's own source with ``ast`` and checks each site
# against the row the contract generated. Static on purpose: the runtime checks
# in ``_send`` only fire on a call that actually happens, which is precisely why
# an UNTESTED method could ship broken. This one sees every site whether or not
# a test exercises it.

CALL_HELPERS = frozenset({"call", "call_none", "call_bytes"})

#: Floor, same reasoning as MINIMUM_OPERATIONS: 16 sites today, and a walk that
#: finds nothing would make every assertion below vacuously true.
MINIMUM_CALL_SITES = 16

LIBRARY_SOURCE = REPO_ROOT / "packages" / "loft-script" / "src" / "loft"


def _literal_dict_keys(node: ast.expr | None) -> set[str] | None:
    """Keys of a literal ``{"a": ...}``, or ``None`` if not statically readable."""
    if not isinstance(node, ast.Dict):
        return None
    keys: set[str] = set()
    for key in node.keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            return None
        keys.add(key.value)
    return keys


def _model_name(node: ast.expr | None) -> str | None:
    """The class name behind ``Model`` or ``Model(...)``, if statically readable."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _call_sites() -> list[tuple[str, ast.Call]]:
    """Every ``…​.call*(ops.X, …)`` in the library, as (location, node).

    Matched on the CALL and on its first argument coming out of ``ops``, not on
    a receiver name: the sites are spelled ``self.session.transport.call``,
    ``session.transport.call``, ``transport.call`` and ``self.transport.call``,
    and a matcher keyed on any one spelling would silently skip the others.
    """
    sites: list[tuple[str, ast.Call]] = []
    for path in sorted(LIBRARY_SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in CALL_HELPERS
                and node.args
                and isinstance(node.args[0], ast.Attribute)
                and isinstance(node.args[0].value, ast.Name)
                and node.args[0].value.id == "ops"
            ):
                sites.append((f"{path.name}:{node.lineno}", node))
    return sites


def test_every_call_site_agrees_with_the_generated_operation() -> None:
    sites = _call_sites()
    assert len(sites) >= MINIMUM_CALL_SITES, (
        f"walked {len(sites)} transport call site(s); expected at least "
        f"{MINIMUM_CALL_SITES}. A walk that finds nothing makes every assertion "
        "below vacuously true — if the surface really shrank, lower the floor "
        "deliberately."
    )

    problems: list[str] = []
    for where, node in sites:
        func = node.func
        assert isinstance(func, ast.Attribute)
        constant = node.args[0]
        assert isinstance(constant, ast.Attribute)
        operation = OPERATIONS_BY_CONSTANT.get(constant.attr)
        if operation is None:
            problems.append(f"{where}: ops.{constant.attr} is not in the table")
            continue

        keywords = {kw.arg: kw.value for kw in node.keywords}

        # (a) the response model the caller parses into must be the one the
        #     contract declares. This is the loop `Transport.call`'s docstring
        #     promises is closed: `model` is passed in rather than resolved from
        #     a string, so only a check like this can tie the two together.
        if func.attr == "call":
            parsed = _model_name(node.args[1]) if len(node.args) > 1 else None
            if parsed != operation.response_model:
                problems.append(
                    f"{where}: parses {parsed!r}; contract declares "
                    f"{operation.response_model!r}"
                )

        # (b) the request body class — statically here, and again at runtime in
        #     `_check_request_model`.
        body = _model_name(keywords.get("body"))
        if body != operation.request_model:
            problems.append(
                f"{where}: sends body {body!r}; contract declares "
                f"{operation.request_model!r}"
            )

        # (c) THE ONE THAT WAS MISSING. A required query parameter absent here
        #     is a 422 before the handler runs, for every input.
        query = _literal_dict_keys(keywords.get("query")) or set()
        if missing := sorted(set(operation.required_query) - query):
            problems.append(
                f"{where}: omits required query parameter(s) {missing} "
                f"({operation.method} {operation.path})"
            )

        # (d) path parameters, exactly — `Operation.url` is strict in both
        #     directions at runtime, so a mismatch here is a guaranteed raise.
        supplied_path = _literal_dict_keys(keywords.get("path_params"))
        if supplied_path is not None and supplied_path != set(operation.path_params):
            problems.append(
                f"{where}: passes path params {sorted(supplied_path)}; route "
                f"declares {sorted(operation.path_params)}"
            )

    assert not problems, "call sites disagree with the contract:\n  " + "\n  ".join(
        problems
    )

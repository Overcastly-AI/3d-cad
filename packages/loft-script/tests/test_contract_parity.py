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
from typing import Any, NamedTuple, cast

import pytest
from loft import _operations as operations_module
from loft._operation import Operation
from loft._operations import OPERATIONS
from pydantic import BaseModel

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
# against the contract. Static on purpose: the runtime checks in ``_send`` only
# fire on a call that actually happens, which is precisely why an UNTESTED
# method could ship broken. This one sees every site whether or not a test
# exercises it.
#
# The EXPECTED side is read straight off ``gateway.openapi.json`` by
# ``_contract_index`` below — never from ``OPERATIONS``. The call sites import
# that table, so checking them against it could only prove the table agrees with
# itself: a generator that mis-read a response ``$ref`` would put the same wrong
# name in the table AND in every site written against it, and a table-based
# check would pass both. The table is used for ONE thing here, addressing
# (constant -> operationId), and even that is cross-checked against the
# contract's method and path.

CALL_HELPERS = frozenset({"call", "call_none", "call_bytes"})

#: Floor, same reasoning as MINIMUM_OPERATIONS: 16 sites today, and a walk that
#: finds nothing would make every assertion below vacuously true.
MINIMUM_CALL_SITES = 16

#: Every library module that talks to the gateway — the walk's declared roots.
#: A GLOBAL floor only notices total collapse; a module whose sites all stopped
#: matching (a renamed ``ops`` import, a new spelling of the call) would take its
#: whole surface out of the check while the other module kept the count above
#: 16. So each root is censused on its own, and a module NOT listed here that
#: grows a site is refused too, which keeps this tuple honest.
CALL_SITE_MODULES = ("part.py", "session.py")

LIBRARY_SOURCE = REPO_ROOT / "packages" / "loft-script" / "src" / "loft"


class ContractShape(NamedTuple):
    """What the contract says a caller of one operation must send and parse."""

    method: str
    path: str
    #: The transport helper the success response admits: ``call`` for a JSON
    #: component, ``call_none`` for an empty body, ``call_bytes`` for a file.
    #: ``None`` when no helper can honour it (untyped JSON, several 2xx codes).
    helper: str | None
    response: str | None
    request: str | None
    path_params: frozenset[str]
    required_query: frozenset[str]


def _ref_name(schema: object) -> str | None:
    if not isinstance(schema, dict):
        return None
    ref = cast("dict[str, Any]", schema).get("$ref")
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None


def _contract_index(contract: dict[str, Any]) -> dict[str, ContractShape]:
    """operationId -> :class:`ContractShape`, derived from the OpenAPI document."""
    index: dict[str, ContractShape] = {}
    for path, item in contract["paths"].items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            responses: dict[str, Any] = operation.get("responses", {})
            success = [code for code in responses if code.startswith("2")]
            helper: str | None = None
            response: str | None = None
            if len(success) == 1:
                content: dict[str, Any] = responses[success[0]].get("content") or {}
                if not content:
                    helper = "call_none"
                elif set(content) == {"application/json"}:
                    response = _ref_name(content["application/json"].get("schema"))
                    helper = "call" if response is not None else None
                elif "application/json" not in content:
                    helper = "call_bytes"
            request_body: dict[str, Any] = operation.get("requestBody") or {}
            body: dict[str, Any] = request_body.get("content") or {}
            body_json: dict[str, Any] = body.get("application/json") or {}
            parameters: list[dict[str, Any]] = operation.get("parameters", [])
            index[operation["operationId"]] = ContractShape(
                method=method.upper(),
                path=path,
                helper=helper,
                response=response,
                request=_ref_name(body_json.get("schema")),
                path_params=frozenset(
                    p["name"] for p in parameters if p["in"] == "path"
                ),
                required_query=frozenset(
                    p["name"]
                    for p in parameters
                    if p["in"] == "query" and p.get("required")
                ),
            )
    return index


def _literal_dict_keys(node: ast.expr | None) -> set[str] | None:
    """Keys of a literal ``{"a": ...}`` (absent = empty); ``None`` if unreadable."""
    if node is None:
        return set()
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


class CallSite(NamedTuple):
    module: str
    where: str
    node: ast.Call


def _is_helper_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in CALL_HELPERS
    )


def _walk_library() -> tuple[list[CallSite], dict[str, int]]:
    """Every ``….call*(ops.X, …)`` in the library, plus a looser census.

    Matched on the CALL and on its first argument coming out of ``ops``, not on
    a receiver name: the sites are spelled ``self.session.transport.call``,
    ``session.transport.call``, ``transport.call`` and ``self.transport.call``,
    and a matcher keyed on any one spelling would silently skip the others.

    The second value counts EVERY ``.call*(`` per module whatever its first
    argument, so a site the strict matcher cannot read (an operation passed
    through a variable) shows up as a disagreement instead of vanishing.
    """
    sites: list[CallSite] = []
    loose: dict[str, int] = {}
    for path in sorted(LIBRARY_SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not _is_helper_call(node):
                continue
            assert isinstance(node, ast.Call)
            loose[path.name] = loose.get(path.name, 0) + 1
            first = node.args[0] if node.args else None
            if (
                isinstance(first, ast.Attribute)
                and isinstance(first.value, ast.Name)
                and first.value.id == "ops"
            ):
                sites.append(CallSite(path.name, f"{path.name}:{node.lineno}", node))
    return sites, loose


def _census(sites: list[CallSite], loose: dict[str, int]) -> list[str]:
    """Refusals about the WALK itself, checked before any site is judged."""
    refusals: list[str] = []
    if len(sites) < MINIMUM_CALL_SITES:
        refusals.append(
            f"walked {len(sites)} transport call site(s); expected at least "
            f"{MINIMUM_CALL_SITES}. If the surface really shrank, lower the floor "
            "deliberately."
        )
    per_module = {name: 0 for name in CALL_SITE_MODULES}
    for site in sites:
        per_module[site.module] = per_module.get(site.module, 0) + 1
    for name, count in sorted(per_module.items()):
        if name not in CALL_SITE_MODULES:
            refusals.append(
                f"{name} has {count} call site(s) but is not in CALL_SITE_MODULES"
            )
        elif count == 0:
            refusals.append(
                f"{name} is a declared root and contributed 0 call sites — the "
                "walk has gone blind to it"
            )
        if loose.get(name, 0) != count:
            refusals.append(
                f"{name}: {loose.get(name, 0)} `.call*(` expression(s) but only "
                f"{count} read as `ops.X` sites — a site is spelled in a way the "
                "walk cannot check"
            )
    return refusals


def _resolve(module: str, name: str) -> type[BaseModel] | None:
    """The object ``name`` is bound to in ``loft.<module>``, if it is a model.

    The name at the site is not enough: ``from loft_wire.parts import
    PartListResponse as PartResponse`` would pass a name comparison while
    parsing into the wrong class.
    """
    bound = getattr(importlib.import_module(f"loft.{module[:-3]}"), name, None)
    if isinstance(bound, type) and issubclass(bound, BaseModel):
        return bound
    return None


def _model_problems(
    where: str,
    role: str,
    module: str,
    name: str | None,
    expected: str | None,
    components: dict[str, Any],
) -> list[str]:
    if name != expected:
        return [f"{where}: {role} {name!r}; contract declares {expected!r}"]
    if name is None or expected is None:
        return []
    model = _resolve(module, name)
    if model is None or model.__name__ != expected:
        return [f"{where}: {role} name {name!r} is bound to {model!r}, not {expected}"]
    fields = {field.alias or key for key, field in model.model_fields.items()}
    declared = set(components[expected].get("properties", {}))
    if fields != declared:
        return [
            f"{where}: {role} {name} has fields {sorted(fields ^ declared)} that "
            f"the contract's {expected} component does not agree on"
        ]
    return []


def _site_problems(
    site: CallSite,
    index: dict[str, ContractShape],
    components: dict[str, Any],
) -> list[str]:
    node, where = site.node, site.where
    func, constant = node.func, node.args[0]
    assert isinstance(func, ast.Attribute) and isinstance(constant, ast.Attribute)
    operation = OPERATIONS_BY_CONSTANT.get(constant.attr)
    if operation is None:
        return [f"{where}: ops.{constant.attr} is not in the table"]
    shape = index.get(operation.operation_id)
    if shape is None or (shape.method, shape.path) != (
        operation.method,
        operation.path,
    ):
        return [f"{where}: ops.{constant.attr} does not address {shape}"]

    problems: list[str] = []
    keywords = {kw.arg: kw.value for kw in node.keywords}

    # (a) the HELPER, derived from the success response. `call_none` on a route
    #     that returns a component throws the fresh state away (and usually
    #     buys a second round trip to re-read it); `call` on a 204 would try to
    #     parse nothing.
    if func.attr != shape.helper:
        problems.append(
            f"{where}: uses {func.attr}; {shape.method} {shape.path} answers "
            f"{shape.response or 'no JSON component'}, which needs {shape.helper}"
        )

    # (b) the model the caller PARSES into. This is the loop `Transport.call`'s
    #     docstring promises is closed: `model` is passed in rather than
    #     resolved from a string, so only a check like this ties the two.
    if func.attr == "call":
        parsed = _model_name(node.args[1]) if len(node.args) > 1 else None
        problems += _model_problems(
            where, "parses", site.module, parsed, shape.response, components
        )

    # (c) the request body class — statically here, and again at runtime in
    #     `_check_request_model`.
    body = _model_name(keywords.get("body"))
    problems += _model_problems(
        where, "sends body", site.module, body, shape.request, components
    )

    # (d) a required query parameter absent here is a 422 before the handler
    #     runs, for every input.
    query = _literal_dict_keys(keywords.get("query"))
    if query is None:
        problems.append(f"{where}: query is not a literal dict; cannot check it")
    elif missing := sorted(shape.required_query - query):
        problems.append(
            f"{where}: omits required query parameter(s) {missing} "
            f"({shape.method} {shape.path})"
        )

    # (e) path parameters, exactly — `Operation.url` is strict in both
    #     directions at runtime, so a mismatch here is a guaranteed raise.
    supplied = _literal_dict_keys(keywords.get("path_params"))
    if supplied is None:
        problems.append(f"{where}: path_params is not a literal dict")
    elif frozenset(supplied) != shape.path_params:
        problems.append(
            f"{where}: passes path params {sorted(supplied)}; route declares "
            f"{sorted(shape.path_params)}"
        )
    return problems


def test_every_call_site_agrees_with_the_contract(contract: dict[str, Any]) -> None:
    sites, loose = _walk_library()
    refusals = _census(sites, loose)
    assert not refusals, "the call-site walk is not trustworthy:\n  " + "\n  ".join(
        refusals
    )

    index = _contract_index(contract)
    components: dict[str, Any] = contract["components"]["schemas"]
    problems = [
        problem for site in sites for problem in _site_problems(site, index, components)
    ]
    assert not problems, "call sites disagree with the contract:\n  " + "\n  ".join(
        problems
    )

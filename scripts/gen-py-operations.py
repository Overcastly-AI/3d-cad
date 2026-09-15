#!/usr/bin/env python3
"""Generate the Python client's gateway OPERATION TABLE (``just gen`` step 3).

Why this generator exists at all, when ``packages/ts-client`` generates whole
TYPES and this one deliberately does not
---------------------------------------------------------------------------
TypeScript cannot read a pydantic model, so the TS client has to re-materialise
the wire types in its own language — that is the ONLY reason
``packages/ts-client`` is generated rather than imported. Python has no such
problem: ``py_kit.schemas`` IS the source of truth, and
``packages/loft-script`` imports those classes directly. Generating a second
set of Python DTOs out of an OpenAPI document that was itself generated out of
those same classes would be a round trip that can only LOSE information
(validators, cross-field model validators, shared derivations like
``is_stale_for_tree``) while adding a drift surface — precisely the
hand-written-duplicate defect CLAUDE.md's DRY rule rejects.

What a Python client genuinely cannot import is the ROUTING: the method, the
URL template, and which component schema the gateway declares as each
operation's request/response body. Those live in the FastAPI decorators, not in
any importable model, so a client that wants them has to copy them — and a copy
is exactly what drifts. So this generator emits that, and only that:

  packages/loft-script/src/loft/_operations.py

one ``Operation`` constant per gateway route, plus an ``OPERATIONS`` mapping
keyed by operationId. ``just gen-check`` diffs it like every other generated
artifact, so a renamed route or a changed request model is CI-red rather than a
404 a user finds at runtime.

The ``request_model`` / ``response_model`` fields are the load-bearing half:
``tests/test_contract_parity.py`` asserts that every model the library actually
SENDS is the class the contract names for that operation. A 2xx only proves the
request parsed — params models are pydantic-default ``extra="ignore"``, so a
misspelled field validates and silently means nothing (CLAUDE.md). Matching the
declared model NAME is a check an ignored field cannot satisfy.

Run from the repo root: ``uv run scripts/gen-py-operations.py [--contracts DIR]
[--out FILE]``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACTS = REPO_ROOT / "packages" / "contracts"
DEFAULT_OUT = REPO_ROOT / "packages" / "loft-script" / "src" / "loft" / "_operations.py"

#: The service whose routes the scripting library speaks to. ONE entry, and
#: that is a boundary decision rather than an oversight: ``apps/web`` talks only
#: to the gateway (CLAUDE.md service boundaries) and the scripting library is
#: another client of the gateway, exactly like the web app. Adding ``documents``
#: or ``geometry`` here would hand scripts a private door the browser lacks.
SERVICE = "gateway"

#: OpenAPI path-item keys that are HTTP verbs.
_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")

#: Stripped from a path before deriving a constant name — every app route lives
#: under it, so keeping it would prefix every constant with the same characters.
_API_PREFIX = "/api/v1"

_NON_IDENT = re.compile(r"[^0-9a-zA-Z]+")

HEADER = "# GENERATED — do not edit; run `just gen`."


def constant_name(method: str, path: str) -> str:
    """``POST`` + ``/api/v1/parts/{part_id}/features``
    -> ``POST_PARTS_PART_ID_FEATURES``.

    Deterministic and readable. Path parameters contribute their NAME, so
    renaming ``{part_id}`` to ``{document_id}`` renames the constant and every
    call site fails pyright — which is the point: a path change should break the
    build, not a user's script.
    """
    tail = path[len(_API_PREFIX) :] if path.startswith(_API_PREFIX) else path
    body = _NON_IDENT.sub("_", tail).strip("_").upper()
    return f"{method.upper()}_{body}" if body else method.upper()


def _mapping(value: object) -> dict[str, Any]:
    """``value`` as a JSON object, or an empty one.

    Every accessor below funnels through this. An OpenAPI document is
    ``dict[str, Any]`` all the way down, and pyright-strict will not let the
    ``Any`` spread silently — which is the right instinct here, because this
    generator's whole job is to read a document it does not control. One
    narrowing point means one place that decides what "not an object" means,
    and it decides on EMPTY rather than on an exception: a route missing a
    ``requestBody`` is ordinary, not an error.
    """
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _sequence(value: object) -> list[Any]:
    """``value`` as a JSON array, or an empty one (see :func:`_mapping`)."""
    return cast(list[Any], value) if isinstance(value, list) else []


def _schema_ref_name(schema: dict[str, Any]) -> str | None:
    """The component NAME behind a ``$ref``, or None for an inline/absent schema."""
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return None
    return ref.rsplit("/", 1)[-1]


def _json_schema(content: dict[str, Any]) -> dict[str, Any]:
    """The ``application/json`` schema of a request/response content map."""
    return _mapping(_mapping(content.get("application/json")).get("schema"))


def _success_response(responses: dict[str, Any]) -> dict[str, Any]:
    """The 2xx response object, lowest status first (200 before 201, ...)."""
    codes = sorted(code for code in responses if str(code).startswith("2"))
    if not codes:
        return {}
    return _mapping(responses[codes[0]])


def collect_operations(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten an OpenAPI document into sorted operation records."""
    operations: list[dict[str, Any]] = []
    paths = _mapping(document.get("paths"))
    for path in sorted(paths):
        item = _mapping(paths[path])
        for method in _METHODS:
            if method not in item:
                continue
            operation = _mapping(item[method])
            parameters = [
                _mapping(entry) for entry in _sequence(operation.get("parameters"))
            ]
            path_params = tuple(
                str(p["name"]) for p in parameters if p.get("in") == "path"
            )
            required_query = tuple(
                str(p["name"])
                for p in parameters
                if p.get("in") == "query" and p.get("required")
            )
            request_body = _mapping(operation.get("requestBody"))
            success = _success_response(_mapping(operation.get("responses")))
            operations.append(
                {
                    "name": constant_name(method, path),
                    "operation_id": str(operation.get("operationId", "")),
                    "method": method.upper(),
                    "path": path,
                    "request_model": _schema_ref_name(
                        _json_schema(_mapping(request_body.get("content")))
                    ),
                    "response_model": _schema_ref_name(
                        _json_schema(_mapping(success.get("content")))
                    ),
                    "path_params": path_params,
                    "required_query": required_query,
                }
            )
    return operations


def _tuple_literal(values: tuple[str, ...]) -> str:
    """A Python source tuple literal; ``()`` for empty, trailing comma otherwise."""
    if not values:
        return "()"
    return "(" + ", ".join(f'"{value}"' for value in values) + ",)"


def render(operations: list[dict[str, Any]]) -> str:
    """Render the module source. Deterministic: sorted input, no timestamps."""
    names = [str(op["name"]) for op in operations]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        # Two routes deriving the same constant would silently shadow one
        # another and the SECOND would win — a client calling the wrong route
        # with a valid-looking payload. Refuse rather than guess.
        raise SystemExit(
            f"gen-py-operations: duplicate constant name(s) {duplicates}; "
            "the name derivation needs to disambiguate them."
        )

    lines: list[str] = [
        HEADER,
        '"""Gateway operation table for the Python scripting client.',
        "",
        f"Source contract: packages/contracts/{SERVICE}.openapi.json.",
        "",
        "One :class:`~loft._operation.Operation` per gateway route. The library",
        "never spells a URL or a method inline — it names an operation here — so a",
        "route that moves is a regenerated table and a pyright error at the call",
        "site, not a 404 a user's script discovers at runtime.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from collections.abc import Mapping",
        "from types import MappingProxyType",
        "from typing import Final",
        "",
        "from loft._operation import Operation",
        "",
    ]
    for op in operations:
        request = f'"{op["request_model"]}"' if op["request_model"] else "None"
        response = f'"{op["response_model"]}"' if op["response_model"] else "None"
        lines.extend(
            [
                f"{op['name']}: Final = Operation(",
                f'    operation_id="{op["operation_id"]}",',
                f'    method="{op["method"]}",',
                f'    path="{op["path"]}",',
                f"    request_model={request},",
                f"    response_model={response},",
                f"    path_params={_tuple_literal(op['path_params'])},",
                f"    required_query={_tuple_literal(op['required_query'])},",
                ")",
                "",
            ]
        )

    lines.extend(
        [
            "#: Every gateway operation, keyed by its OpenAPI ``operationId``. Lets a",
            "#: caller (and the contract-parity test) enumerate the whole surface",
            "#: without importing each constant by name.",
            "OPERATIONS: Final[Mapping[str, Operation]] = MappingProxyType(",
            "    {",
        ]
    )
    for op in operations:
        lines.append(f'        "{op["operation_id"]}": {op["name"]},')
    lines.extend(["    }", ")", ""])
    return "\n".join(lines)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    contract: Path = args.contracts / f"{SERVICE}.openapi.json"
    document: dict[str, Any] = _mapping(
        json.loads(contract.read_text(encoding="utf-8"))
    )
    operations = collect_operations(document)
    if not operations:
        # A generator that emits an EMPTY table makes every "the library only
        # calls declared operations" assertion vacuously true — the
        # gate-that-examines-nothing class CLAUDE.md documents. Refuse.
        raise SystemExit(
            f"gen-py-operations: {contract} declares no operations; refusing to "
            "write an empty table."
        )
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(operations), encoding="utf-8")
    print(
        f"gen-py-operations: wrote {os.path.relpath(out)} "
        f"({len(operations)} operations)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

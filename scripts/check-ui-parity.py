#!/usr/bin/env python3
"""Measure what the BACKEND can do against what a USER can actually reach.

Founder, 2026-08-26: "There are features that exist on the backend but not the
front end." True, and until now nobody could say WHICH, because the question was
being answered from memory. This answers it from the committed contract.

THE DISTINCTION THAT MAKES THIS HONEST — and the reason a naive grep is worse
than useless here. Every capability literal in the gateway contract falls into
one of two classes, and they have OPPOSITE correct answers:

  * REQUEST-side (a constraint `kind`, a feature type, an export format): the
    user SENDS it. If the UI cannot author it, the capability is unreachable and
    that is a gap.
  * RESPONSE-side (`not_converged`, `over_constrained`, a solve status): the
    service SENDS it and the UI DISPLAYS it. Render-only is exactly right, and
    flagging it would be noise that trains everyone to ignore the report.

So reachability is computed only for literals reachable from a requestBody. A
tool that flagged both would have a longer list and less meaning.

Three tiers, and the middle one is the founder's actual complaint:

  ABSENT       the literal appears nowhere under apps/web/src.
  RENDER-ONLY  it appears in app source but no e2e spec drives it. The app can
               DISPLAY the thing and no user can CREATE it. `symmetric_lines`
               and `collinear` shipped in exactly this state: rendered by
               ConstraintGlyphs.tsx, authorable by nobody.
  AUTHORABLE   an e2e spec exercises it, i.e. a path through the real UI exists.

The e2e suite is the reachability oracle on purpose. It drives the real browser,
so "a spec creates this" is the closest mechanical proxy we have for "a user
can". It is a PROXY: a spec that only asserts on a fixture seeded over the API
proves nothing about the UI, which is why gaps are reported for a human to
judge rather than auto-closed.

Matching is word-boundary and quoted (`"foo"`, `'foo'`, `` `foo` ``). Bare
substring matching reports `angle` as reachable because `rectangle` exists,
which is how a parity check ends up confidently wrong.

Usage:
    python3 scripts/check-ui-parity.py              # report, exit 0
    python3 scripts/check-ui-parity.py --strict     # exit 1 if any gap
    python3 scripts/check-ui-parity.py --json       # machine-readable
    python3 scripts/check-ui-parity.py --self-test  # prove it can fail
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATEWAY_SPEC = REPO / "packages" / "contracts" / "gateway.openapi.json"
WEB_SRC = REPO / "apps" / "web" / "src"
WEB_E2E = REPO / "apps" / "web" / "e2e"

#: A literal has to look like a discriminator to be worth checking. Free-text
#: enum members (names, descriptions) are not capabilities.
LITERAL_RE = re.compile(r"^[a-z][a-z0-9_]{2,}$")

#: Literals that are genuinely not user-authorable even though they reach a
#: request body. Keep this list SHORT and justified — every entry is a place the
#: tool has been told to stop looking.
EXEMPT = {
    # Echoed back on a round-trip; the UI never composes one from scratch.
    "unknown",
}


def _load_spec(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def _schema_literals(node: object, into: set[str]) -> None:
    """Every string const/enum member anywhere under `node`."""
    if isinstance(node, dict):
        const = node.get("const")
        if isinstance(const, str):
            into.add(const)
        for member in node.get("enum") or []:
            if isinstance(member, str):
                into.add(member)
        for value in node.values():
            _schema_literals(value, into)
    elif isinstance(node, list):
        for value in node:
            _schema_literals(value, into)


def _refs(node: object, into: set[str]) -> None:
    """Every `#/components/schemas/X` reference anywhere under `node`."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            into.add(ref.rsplit("/", 1)[1])
        for value in node.values():
            _refs(value, into)
    elif isinstance(node, list):
        for value in node:
            _refs(value, into)


def request_side_schemas(spec: dict) -> set[str]:
    """Schema names reachable from any operation's requestBody.

    Transitively closed: a constraint `kind` lives several $refs below the
    request body that carries it, and stopping at depth one would miss exactly
    the nested discriminated unions this check exists to find.
    """
    schemas = spec.get("components", {}).get("schemas", {})
    seeds: set[str] = set()
    for methods in spec.get("paths", {}).values():
        if not isinstance(methods, dict):
            continue
        for operation in methods.values():
            if isinstance(operation, dict) and "requestBody" in operation:
                _refs(operation["requestBody"], seeds)

    seen: set[str] = set()
    queue = list(seeds)
    while queue:
        name = queue.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        nested: set[str] = set()
        _refs(schemas[name], nested)
        queue.extend(nested - seen)
    return seen


def request_literals(spec: dict) -> dict[str, set[str]]:
    """Candidate capability literals -> the request-side schemas carrying them."""
    schemas = spec.get("components", {}).get("schemas", {})
    owners: dict[str, set[str]] = {}
    for name in request_side_schemas(spec):
        found: set[str] = set()
        _schema_literals(schemas[name], found)
        for literal in found:
            if LITERAL_RE.match(literal) and literal not in EXEMPT:
                owners.setdefault(literal, set()).add(name)
    return owners


def _quoted(literal: str) -> re.Pattern[str]:
    return re.compile(r"""["'`]""" + re.escape(literal) + r"""["'`]""")


def _corpus(root: Path) -> str:
    if not root.exists():
        return ""
    return "\n".join(
        path.read_text(errors="ignore")
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )


def classify(spec: dict, src: str, e2e: str) -> list[tuple[str, str, list[str]]]:
    rows: list[tuple[str, str, list[str]]] = []
    for literal, owners in sorted(request_literals(spec).items()):
        pattern = _quoted(literal)
        if not pattern.search(src):
            tier = "ABSENT"
        elif not pattern.search(e2e):
            tier = "RENDER-ONLY"
        else:
            tier = "AUTHORABLE"
        rows.append((literal, tier, sorted(owners)))
    return rows


def _self_test() -> int:
    """Prove the check CAN fail, and that each tier is distinguishable.

    A parity report that cannot go red is a parity report nobody should trust —
    this repo has shipped five gates that could not fail, so a gate now ships
    with the mutation that reddens it.
    """
    spec = {
        "paths": {
            "/thing": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Req"}
                            }
                        }
                    }
                }
            },
            "/status": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Resp"}
                                }
                            }
                        }
                    }
                }
            },
        },
        "components": {
            "schemas": {
                "Req": {
                    "properties": {"body": {"$ref": "#/components/schemas/Nested"}}
                },
                # Nested one level below the request body: the discriminated-union
                # shape the real contract uses, and the case a depth-one walk misses.
                "Nested": {
                    "properties": {"kind": {"enum": ["wired", "drawn", "angle"]}}
                },
                "Resp": {"properties": {"status": {"enum": ["responseonly"]}}},
            }
        },
    }
    # `angle` is the ABSENT case and the substring trap in one: the corpus below
    # contains "rectangle" and "triangle" but never the literal `angle`, so a
    # naive `in` test calls it reachable. That is the real defect this fixture
    # has to be able to catch — the first version used three non-overlapping
    # words, which made the negative control unfalsifiable, and the self-test
    # said so on its first run.
    src = 'const a = "wired"; const b = "drawn"; const c = "rectangle";'
    e2e = 'await page.click("wired"); drawTriangle("triangle");'
    tiers = {literal: tier for literal, tier, _ in classify(spec, src, e2e)}

    failures: list[str] = []
    for literal, want in (
        ("wired", "AUTHORABLE"),
        ("drawn", "RENDER-ONLY"),
        ("angle", "ABSENT"),
    ):
        if tiers.get(literal) != want:
            failures.append(f"  {literal}: want {want}, got {tiers.get(literal)}")

    # A response-only literal must not be reported AT ALL. This is the assertion
    # that keeps the report meaningful rather than merely long.
    if "responseonly" in tiers:
        failures.append("  responseonly: a response-side literal was reported as a gap")

    # Count floor: `all([])` is True, so a walk that found nothing would satisfy
    # every assertion above by vacuity. Same shape as the four gates that shipped
    # unable to fail.
    if len(tiers) != 3:
        failures.append(f"  expected exactly 3 request-side literals, got {len(tiers)}")

    # Negative control: bare-substring matching must get this fixture WRONG. If
    # it agrees with the real classifier, the word-boundary logic is untested and
    # the fixture is decorative. `angle` is the discriminator — "rectangle" is in
    # src and "triangle" in e2e, so substring matching calls it AUTHORABLE where
    # the truth is ABSENT.
    naive = {
        literal: (
            "AUTHORABLE"
            if literal in e2e
            else "RENDER-ONLY"
            if literal in src
            else "ABSENT"
        )
        for literal in ("wired", "drawn", "angle")
    }
    if naive.get("angle") != "AUTHORABLE":
        failures.append(
            "  the fixture cannot tell quoted matching from substring matching "
            f"(naive says angle={naive.get('angle')}, "
            "wanted the WRONG answer AUTHORABLE)"
        )

    if failures:
        print("self-test FAILED:")
        print("\n".join(failures))
        return 1
    print("self-test passed: 3 request-side literals, one per tier;")
    print("  response-side literal correctly not reported;")
    print("  nested-below-requestBody literal correctly reached;")
    print("  substring-matching negative control fires.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 if any gap")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--self-test", action="store_true", help="prove it can fail")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    rows = classify(_load_spec(GATEWAY_SPEC), _corpus(WEB_SRC), _corpus(WEB_E2E))
    gaps = [row for row in rows if row[1] != "AUTHORABLE"]

    if args.json:
        print(
            json.dumps(
                [
                    {"literal": literal, "tier": tier, "schemas": owners}
                    for literal, tier, owners in rows
                ],
                indent=2,
            )
        )
    else:
        total = len(rows)
        print(
            f"UI parity — {total} request-side capability literals "
            "in the gateway contract\n"
        )
        for tier in ("ABSENT", "RENDER-ONLY"):
            named = [row for row in rows if row[1] == tier]
            if not named:
                continue
            note = (
                "nowhere in apps/web/src — no user can reach these"
                if tier == "ABSENT"
                else "in app source, but no e2e spec drives one — "
                "displayable, not authorable"
            )
            print(f"{tier}  ({len(named)}) — {note}")
            for literal, _, owners in named:
                print(f"    {literal:<28} {', '.join(owners[:3])}")
            print()
        reachable = total - len(gaps)
        print(f"AUTHORABLE: {reachable}/{total}")

    if args.strict and gaps:
        print(
            f"::error::{len(gaps)} backend capabilities are not reachable from the UI"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

A FOURTH TIER, added after the first real run and now the one that earns its
keep: UNCALLED OPERATIONS. The literal tiers answer "can the user pick this
VALUE", which quietly presumes the route carrying it is called at all. It is
often not. The first run surfaced one true literal gap and MISSED three whole
shipped capabilities with no caller anywhere — reorder the feature tree, import
a STEP assembly, a drawing's parts list. Path SHAPES are far more distinctive
than words (`bom` is ambiguous, `drawings/{id}/bom` is not), so this tier has no
false positives at all, which is more than the literal tiers can say.

MATCHING, and every rule here exists because its absence produced a wrong answer
on the real repo:

  * Quoted (`"foo"`) OR as a `-`/`_`-delimited token inside a quoted string, so
    `combine-op-subtract` counts as driving `subtract`. Specs address controls by
    testid or keystroke, essentially never by the bare literal — quoted-only
    matching called ~20 of 29 flagged rows unreachable when every one was driven.
  * Never bare substring: that reports `angle` as reachable because `rectangle`
    exists.
  * For AMBIGUOUS common words, presence is not evidence — a driving verb must
    appear within a few lines. `midpoint` read AUTHORABLE purely because specs
    discuss snap midpoints in prose.

KNOWN RESIDUAL, stated rather than hidden. This is a heuristic and both error
directions survive in the current output:
  * FALSE AUTHORABLE: `midpoint` STILL reads reachable — the snap specs that
    mention it also click things, so the verb-proximity guard passes. It is in
    fact keyboard-only (`m`) and absent from the sketch strip's groups. A false
    AUTHORABLE retires an open gap silently, so treat the AUTHORABLE tier as
    "probably fine", never as proof.
  * FALSE RENDER-ONLY: `tangent` and `equal` are driven by `keyboard.press("t")`
    with the literal nowhere in the spec; `simple` is driven through
    `hole-depth-blind`. A dozen such rows remain.
A STRUCTURAL BLIND SPOT, distinct from the noise above: THIS MEASURES
REACHABILITY, NOT DISCOVERABILITY, and the two come apart in a way that matters.
Found 2026-08-27 on SKETCH-VOCAB-1. All five new sketch constraints counted
AUTHORABLE — correctly, since the selection-driven offer rail proposes each one
and specs drive them. But four of them had **no row anywhere in the product's
constraint catalogue**, and the gap is structural rather than an oversight: an
offer only appears once the selection already fits, so the rail can PROPOSE a
verb and can never TEACH you to reach one. From an empty or wrong selection they
were invisible. A user who does not already know the verb exists cannot find it,
and this script reports 100 % reachable.

So a batch that closes real discoverability gaps will leave the number UNMOVED,
and that is the honest outcome — a spec written to move it would be measuring the
wrong thing. Never treat a flat count as a batch that achieved nothing, and never
let "make the number go up" become the goal.

Triage the report by opening the source. It is a search-ordering tool, not a
verdict, and the workflow's Parity phase is instructed to say what it checked.

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
from typing import Any, cast

#: An OpenAPI document. Deliberately `Any`-valued: the spec is arbitrary
#: JSON and every walker below is written to tolerate any shape it meets.
Spec = dict[str, Any]

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
    # Internal prefetch/scrub hints the app emits programmatically. There is no
    # user verb here and there should not be one.
    "feature_edit",
    "travel_stop",
    # The server's fallback discriminator for a non-analytic edge — read off a
    # pick, never chosen by a human.
    "other",
    # The primitive-shape dev seam that predates the feature tree. Parts are
    # authored as features; offering a naked primitive would teach the wrong model.
    "cylinder",
}

#: Schemas whose values are DATA, served at runtime and rendered into a picker —
#: so no value can ever appear in app source, by design. `MaterialSection.tsx`
#: builds its options from `GET /api/v1/materials` with `library.map`, and
#: hardcoding the keys in `apps/web` would be the second-copy-of-the-table DRY
#: violation that endpoint exists to prevent. Flagging these would be punishing
#: the correct implementation.
DATA_DRIVEN_SCHEMAS = {
    "MaterialAssignment",
    "BodyMaterialAssignment",
    "BodyLumpInfo",
}


def _load_spec(path: Path) -> Spec:
    with path.open() as handle:
        loaded: Spec = json.load(handle)
        return loaded


def _schema_literals(node: object, into: set[str]) -> None:
    """Every string const/enum member anywhere under `node`."""
    if isinstance(node, dict):
        mapping = cast(Spec, node)
        const = mapping.get("const")
        if isinstance(const, str):
            into.add(const)
        for member in cast("list[Any]", mapping.get("enum") or []):
            if isinstance(member, str):
                into.add(member)
        for value in mapping.values():
            _schema_literals(value, into)
    elif isinstance(node, list):
        for value in cast("list[Any]", node):
            _schema_literals(value, into)


def _refs(node: object, into: set[str]) -> None:
    """Every `#/components/schemas/X` reference anywhere under `node`."""
    if isinstance(node, dict):
        mapping = cast(Spec, node)
        ref = mapping.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            into.add(ref.rsplit("/", 1)[1])
        for value in mapping.values():
            _refs(value, into)
    elif isinstance(node, list):
        for value in cast("list[Any]", node):
            _refs(value, into)


def request_side_schemas(spec: Spec) -> set[str]:
    """Schema names reachable from any operation's requestBody.

    Transitively closed: a constraint `kind` lives several $refs below the
    request body that carries it, and stopping at depth one would miss exactly
    the nested discriminated unions this check exists to find.
    """
    schemas: Spec = spec.get("components", {}).get("schemas", {})
    seeds: set[str] = set()
    paths: Spec = spec.get("paths", {})
    for methods in paths.values():
        if not isinstance(methods, dict):
            continue
        for operation in cast(Spec, methods).values():
            if isinstance(operation, dict) and "requestBody" in operation:
                _refs(cast(Spec, operation)["requestBody"], seeds)

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


def request_literals(spec: Spec) -> dict[str, set[str]]:
    """Candidate capability literals -> the request-side schemas carrying them."""
    schemas: Spec = spec.get("components", {}).get("schemas", {})
    owners: dict[str, set[str]] = {}
    for name in request_side_schemas(spec):
        if name in DATA_DRIVEN_SCHEMAS:
            continue
        found: set[str] = set()
        _schema_literals(schemas[name], found)
        for literal in found:
            if LITERAL_RE.match(literal) and literal not in EXEMPT:
                owners.setdefault(literal, set()).add(name)
    # A literal owned ONLY by data-driven schemas is reachable by construction.
    return {
        literal: names
        for literal, names in owners.items()
        if not names <= DATA_DRIVEN_SCHEMAS
    }


#: An e2e spec almost never writes the bare literal. It addresses a control by
#: testid — `combine-op-subtract`, `hole-depth-blind`, `pattern-kind-circular` —
#: or by keystroke, `keyboard.press("t")` for tangent. Matching only the quoted
#: form produced ~20 false RENDER-ONLY rows out of 29 on the first real run:
#: every one of union/subtract/intersect/sweep/simple/blind/iso_metric/stl/glb
#: is driven by a spec that never spells the literal.
def _reachable_in(literal: str, corpus: str) -> bool:
    quoted = r"""["'`]""" + re.escape(literal) + r"""["'`]"""
    # ...as a `-`/`_`-delimited token inside any quoted string, which is what a
    # testid looks like. Anchored on delimiters so `angle` still does not match
    # `rectangle`, but `combine-op-subtract` does match `subtract`.
    token = (
        r"""["'`][a-z0-9_-]*[-_]"""
        + re.escape(literal)
        + r"""(?:[-_][a-z0-9_-]*)?["'`]"""
    )
    lead = r"""["'`]""" + re.escape(literal) + r"""[-_][a-z0-9_-]*["'`]"""
    return bool(re.search(f"{quoted}|{token}|{lead}", corpus))


#: Words common enough to appear in ordinary spec prose. For these, presence is
#: not evidence — `midpoint` was reported AUTHORABLE purely because specs discuss
#: snap midpoints and edge midpoints, while the constraint itself is bound to `m`
#: and absent from the sketch strip entirely. A FALSE AUTHORABLE is the failure
#: that matters: it retires a gap that is still open, silently and forever.
AMBIGUOUS = {
    "angle",
    "circular",
    "closed",
    "equal",
    "lock",
    "midpoint",
    "note",
    "other",
    "simple",
    "measured",
    "features",
    "scope",
}

#: An authoring verb near the literal is what turns presence into evidence.
AUTHORING = re.compile(
    r"\b(click|press|selectOption|fill|check|tap|dragTo|setInputFiles)\b"
)


def _authored_in(literal: str, corpus: str) -> bool:
    """For an ambiguous word, demand a driving verb within a few lines."""
    lines = corpus.splitlines()
    for index, line in enumerate(lines):
        if _reachable_in(literal, line):
            window = "\n".join(lines[max(0, index - 4) : index + 5])
            if AUTHORING.search(window):
                return True
    return False


def _corpus(root: Path) -> str:
    if not root.exists():
        return ""
    return "\n".join(
        path.read_text(errors="ignore")
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )


def operations(spec: Spec) -> list[tuple[str, str]]:
    """(method, path) for every operation the gateway exposes."""
    found: list[tuple[str, str]] = []
    paths: Spec = spec.get("paths", {})
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method in cast(Spec, methods):
            if str(method).lower() in {"get", "post", "put", "patch", "delete"}:
                found.append((str(method).upper(), str(path)))
    return found


def _path_pattern(path: str) -> re.Pattern[str]:
    """A regex matching how the web app writes this path in a template literal.

    `/api/v1/parts/{part_id}/features/order` has to match
    `` `/parts/${partId}/features/order` `` — so each {param} becomes a
    one-segment wildcard and the `/api/v1` prefix is dropped, since callers
    mount it via the client's base URL.
    """
    trimmed = re.sub(r"^/api/v\d+", "", path)
    parts = [
        r"[^/\"'`]+" if segment.startswith("{") else re.escape(segment)
        for segment in trimmed.strip("/").split("/")
        if segment
    ]
    return re.compile("/".join(parts))


def unreachable_operations(spec: Spec, src: str) -> list[tuple[str, str]]:
    """Operations whose path SHAPE appears nowhere in the web app.

    THE TIER THAT ACTUALLY FINDS THINGS. Literal-matching answers "can the user
    pick this VALUE", which presumes the route carrying it is called at all —
    and on the first real run it surfaced exactly one true gap while missing
    three whole shipped capabilities with no caller whatsoever: reorder the
    feature tree, import a STEP assembly, and a drawing's parts list. Measured
    zero false positives, because a path shape is far more distinctive than a
    word: `bom` alone is ambiguous (an assembly BOM client already exists),
    `drawings/{id}/bom` is not.
    """
    return [
        (method, path)
        for method, path in operations(spec)
        if not _path_pattern(path).search(src)
    ]


def classify(spec: Spec, src: str, e2e: str) -> list[tuple[str, str, list[str]]]:
    rows: list[tuple[str, str, list[str]]] = []
    for literal, owners in sorted(request_literals(spec).items()):
        if not _reachable_in(literal, src):
            tier = "ABSENT"
        elif literal in AMBIGUOUS:
            # Presence proves nothing for a common word; demand a driving verb.
            tier = "AUTHORABLE" if _authored_in(literal, e2e) else "RENDER-ONLY"
        elif not _reachable_in(literal, e2e):
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

    # --- The two failure modes the first version shipped with, both measured on
    # --- the real repo before being fixed. Each gets a fixture that reproduces it.

    # (1) FALSE RENDER-ONLY. A spec addresses a control by TESTID, never by the
    # bare literal — `combine-op-subtract` drives `subtract`. Quoted-only matching
    # called ~20 of 29 flagged rows unreachable when every one was driven.
    testid_spec = {
        "paths": {
            "/x": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Op"}
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {"Op": {"properties": {"op": {"enum": ["subtract"]}}}}
        },
    }
    testid_tiers = {
        literal: tier
        for literal, tier, _ in classify(
            testid_spec,
            'testid="combine-op-subtract"',
            'await page.getByTestId("combine-op-subtract").click();',
        )
    }
    if testid_tiers.get("subtract") != "AUTHORABLE":
        failures.append(
            f"  subtract: driven via a testid, want AUTHORABLE, "
            f"got {testid_tiers.get('subtract')}"
        )

    # (2) FALSE AUTHORABLE — the direction that RETIRES an open gap, silently.
    # `midpoint` was reported reachable purely because specs discuss snap
    # midpoints and edge midpoints in prose; the constraint is keyboard-only and
    # absent from the sketch strip. Presence of an ambiguous word is not evidence.
    ambiguous_spec = {
        "paths": {
            "/y": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/C"}
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {"C": {"properties": {"kind": {"enum": ["midpoint"]}}}}
        },
    }
    prose = '// snapping to the "midpoint" of the edge\nexpect(x).toBe(1);'
    ambiguous_tiers = {
        literal: tier
        for literal, tier, _ in classify(ambiguous_spec, '"midpoint"', prose)
    }
    if ambiguous_tiers.get("midpoint") != "RENDER-ONLY":
        failures.append(
            "  midpoint: mentioned in prose with no authoring verb, want "
            f"RENDER-ONLY, got {ambiguous_tiers.get('midpoint')}"
        )
    driven = {
        literal: tier
        for literal, tier, _ in classify(
            ambiguous_spec,
            '"midpoint"',
            'await page.getByTestId("constraint-midpoint").click();',
        )
    }
    if driven.get("midpoint") != "AUTHORABLE":
        failures.append(
            "  midpoint: actually driven, want AUTHORABLE, "
            f"got {driven.get('midpoint')}"
        )

    # (3) The operation tier — the one that found three whole shipped
    # capabilities with no caller, which no literal check can see.
    op_spec: Spec = {
        "paths": {
            "/api/v1/parts/{part_id}/features/order": {"put": {}},
            "/api/v1/parts/{part_id}/features": {"post": {}},
        }
    }
    orphans = unreachable_operations(op_spec, "`/parts/${id}/features`")
    if [p for _, p in orphans] != ["/api/v1/parts/{part_id}/features/order"]:
        failures.append(
            f"  operation tier: want only .../features/order uncalled, got {orphans}"
        )

    if failures:
        print("self-test FAILED:")
        print("\n".join(failures))
        return 1
    print("self-test passed:")
    print("  3 request-side literals, one per tier;")
    print("  response-side literal correctly not reported;")
    print("  nested-below-requestBody literal correctly reached;")
    print("  substring-matching negative control fires;")
    print("  a testid-driven literal reads AUTHORABLE (false RENDER-ONLY);")
    print("  an ambiguous word in prose reads RENDER-ONLY (false AUTHORABLE);")
    print("  an uncalled operation is found while its called sibling is not.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 if any gap")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--self-test", action="store_true", help="prove it can fail")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    spec = _load_spec(GATEWAY_SPEC)
    src = _corpus(WEB_SRC)
    rows = classify(spec, src, _corpus(WEB_E2E))
    gaps = [row for row in rows if row[1] != "AUTHORABLE"]
    orphans = unreachable_operations(spec, src)

    if args.json:
        print(
            json.dumps(
                {
                    "literals": [
                        {"literal": literal, "tier": tier, "schemas": owners}
                        for literal, tier, owners in rows
                    ],
                    "uncalledOperations": [
                        {"method": method, "path": path} for method, path in orphans
                    ],
                },
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
        if orphans:
            print(
                f"UNCALLED OPERATIONS  ({len(orphans)}) — the gateway exposes "
                "these and nothing in apps/web calls them"
            )
            for method, path in orphans:
                print(f"    {method:<7} {path}")
            print()
        reachable = total - len(gaps)
        print(f"AUTHORABLE: {reachable}/{total} literals; ", end="")
        print(
            f"{len(operations(spec)) - len(orphans)}/{len(operations(spec))} "
            "operations called"
        )
        print(
            "\nSCOPE: desktop-and-mouse. A capability whose only route is a "
            "multi-entity\nselection is counted AUTHORABLE here and is "
            "unreachable on touch — measured\n2026-08-27: a second tap replaces "
            "the selection, and so does a 900 ms long press."
        )

    if args.strict and (gaps or orphans):
        print(
            f"::error::{len(gaps)} capability literal(s) and {len(orphans)} whole "
            "operation(s) are not reachable from the UI"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

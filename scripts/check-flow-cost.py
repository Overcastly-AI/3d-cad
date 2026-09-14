#!/usr/bin/env python3
"""Measure what a JOURNEY COSTS THE HAND — gestures per task, from the e2e suite.

Founder, 2026-09-11: "The flow of creating a part should be seamless."

`check-ui-parity.py` answers "can the user reach this at all", and it says so
itself in its own docstring: it measures REACHABILITY, NOT DISCOVERABILITY, and
a batch that closes real flow gaps will leave its number unmoved. That is the
seam this script occupies. Every FB-1..FB-19 founder report was a flow failure
where the capability was already present, already reachable, already covered by
a green spec — and cost too much to get to. Parity is structurally blind to all
of them, because a capability that takes eleven gestures is AUTHORABLE.

THE CORPUS NOBODY WAS READING AS ONE. `apps/web/e2e/` holds 147 specs that drive
the real browser through real UI paths. That is not just a test suite, it is a
recorded transcript of ~2500 user gestures on this product — the only such
record we have. Counting them per journey turns "does creating a part feel
seamless" from an opinion into a number that MOVES when a redesign shortens the
path, and that can be re-derived by anyone.

WHAT COUNTS AS ONE GESTURE, and the one decision here that is load-bearing:

  * click / dblclick / tap / fill / press / type / selectOption / check /
    setChecked / wheel / dragTo  ->  1 each.
  * A `mouse.down() ... mouse.move()* ... mouse.up()` run  ->  **1**, not 4-6.
  * A bare `mouse.move()` or `.hover()` outside a drag  ->  **0**. Aiming is not
    committing; the click that follows is the act.

THAT DRAG RULE IS THE WHOLE POINT AND IT IS NOT A CONVENIENCE. Playwright spells
one drag as move-down-move-move-up. Counted naively, `extrude-drag-handle.spec.ts`
scores its direct-manipulation path as FIVE TIMES more expensive than the modal
form it replaces — so the metric would have argued, with a straight face and real
numbers, for deleting the drag handle and keeping the form. A metric that
punishes the exact behaviour the design mandate demands more of is worse than no
metric, because it comes with authority. Collapsing the run is what makes this
measure the HAND rather than the wire.

HELPER EXPANSION, without which the number is fiction. `full-flow.spec.ts` reads
as a handful of calls; `enterSketch()` alone is two clicks and half the specs
route their real work through `support.ts`. So local and imported helpers are
resolved and their cost folded into the caller, recursively, with a cycle guard.
Unexpanded, the canonical create-a-part journey undercounts by more than half.

API SHORTCUTS ARE SUBTRACTED FROM THE CLAIM, NOT FROM THE COUNT. `seedSession`
and `createPartViaApi` seed over the API. A spec that uses them has a low
gesture count because it SKIPPED part of the journey, not because that part is
cheap — the single most dangerous reading this data supports. Such journeys are
tagged `partial` and are never comparable with an end-to-end one. Report the tag
next to the number or do not report the number.

WHAT THIS CANNOT SEE — state these with the number, every time:

  1. It measures the path THE SPEC TOOK, not the shortest path the app affords,
     and not the path a new user would find. A spec author pressing `e` records
     one gesture where a user hunting a toolbar spends four and a half seconds.
     The count therefore models an EXPERT who already knows every verb. That is
     a real user worth optimising for, and it is not the user FB-16 was about.
  2. It is blind to hesitation, hunting, ambiguity and dread — which is where
     the founder's reports actually lived. FB-13 (a key that sometimes saves and
     sometimes discards) costs ZERO gestures and was the worst defect on the
     list, because its cost is paid in the pause before each one.
  3. It is trivially gamed by rewriting the spec instead of the app. A drop in
     this number is a QUESTION ("what changed?"), never an achievement. Pair
     every movement with the diff that caused it, or do not claim it.

So: a search-ordering tool and a conversation-starter, exactly like the parity
report. Not a gate, and deliberately shipped with no `--strict`.

Usage:
    python3 scripts/check-flow-cost.py                 # ranked journeys
    python3 scripts/check-flow-cost.py --json          # machine-readable
    python3 scripts/check-flow-cost.py --journey sketch  # filter by title/file
    python3 scripts/check-flow-cost.py --self-test     # prove it can fail
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TypedDict


class Journey(TypedDict):
    """One `test()` block: a recorded user journey and what it cost the hand."""

    spec: str
    title: str
    gestures: int
    #: Names of the API-seeding helpers it reached, i.e. the parts of the
    #: journey it did NOT measure. Empty means everything went through the UI.
    skipped: list[str]


REPO = Path(__file__).resolve().parent.parent
E2E = REPO / "apps" / "web" / "e2e"

#: One gesture each. `down`/`up`/`move` are handled separately — they are the
#: spelling of a drag, not four acts.
COMMIT_VERBS = (
    "click",
    "dblclick",
    "tap",
    "fill",
    "press",
    "type",
    "selectOption",
    "check",
    "uncheck",
    "setChecked",
    "dragTo",
    "wheel",
)

_ACTION_RE = re.compile(
    r"\.(" + "|".join([*COMMIT_VERBS, "down", "up"]) + r")\s*\(",
)

#: Helpers that seed state over the API instead of driving the UI. A journey
#: touching one of these is PARTIAL — see the docstring. Keep this list short
#: and justified; every entry silently reclassifies journeys.
API_SHORTCUTS = {
    "seedSession",
    "seedStoredSession",
    "registerViaApi",
    "createPartViaApi",
}

#: A call to a helper we know the cost of. Deliberately not a general JS parser:
#: an identifier followed by `(`, which over-matches (`Math.max(`, `Number(`) and
#: is harmless, because only names present in the resolved helper table count.
_CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")

#: `async function foo(` / `function foo(` / `const foo = async (` / `= (`
_FN_DECL_RE = re.compile(
    r"(?:(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*[(<])"
    r"|(?:(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?[(<])",
)


def _own_gestures(body: str) -> int:
    """Gestures written literally in `body`, collapsing each drag run to one."""
    n = 0
    dragging = False
    for m in _ACTION_RE.finditer(body):
        verb = m.group(1)
        if verb == "down":
            # A nested/repeated down inside an unterminated run is still one
            # drag; only the first opens it.
            if not dragging:
                dragging = True
                n += 1
            continue
        if verb == "up":
            dragging = False
            continue
        if dragging:
            # move/click chatter between down and up is the drag's own spelling.
            continue
        n += 1
    return n


def _block_at(src: str, open_idx: int) -> str:
    """Source of the braced block whose opening `{` is at or after `open_idx`.

    String- and comment-naive by design: a stray brace inside a string literal
    would truncate a block. Cross-checked against the real suite — see
    `--self-test`'s coverage assertion, which fails loudly if the extracted
    blocks stop accounting for the file's own gestures.
    """
    start = src.find("{", open_idx)
    if start < 0:
        return ""
    depth = 0
    for i in range(start, len(src)):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    return src[start:]


def _skip_params(src: str, idx: int) -> int:
    """Index just past a declaration's parameter list, starting at `(` or `<`.

    Needed because a TypeScript parameter can be typed with an object literal —
    `s1: { x: number; y: number }` — and "the first `{` after the name" then
    lands inside the signature. That is not hypothetical: it made
    `runFullFlow()`, the canonical register-to-export journey and the most
    important row this script prints, report **0 gestures**. Zero is the
    failure shape this repo has shipped five times, because it reads as a clean
    answer rather than a missing one. Balanced-paren matching steps over the
    whole signature, braces and all.
    """
    n = len(src)
    if idx < n and src[idx] == "<":
        depth = 0
        while idx < n:
            if src[idx] == "<":
                depth += 1
            elif src[idx] == ">":
                depth -= 1
                if depth == 0:
                    idx += 1
                    break
            idx += 1
        while idx < n and src[idx] not in "(":
            idx += 1
    if idx >= n or src[idx] != "(":
        return idx
    depth = 0
    while idx < n:
        if src[idx] == "(":
            depth += 1
        elif src[idx] == ")":
            depth -= 1
            if depth == 0:
                return idx + 1
        idx += 1
    return n


def _declared_functions(src: str) -> dict[str, str]:
    """name -> body source, for every function declared in `src`."""
    out: dict[str, str] = {}
    for m in _FN_DECL_RE.finditer(src):
        name = m.group(1) or m.group(2)
        body = _block_at(src, _skip_params(src, m.end() - 1))
        if name and body:
            out[name] = body
    return out


def _resolve_costs(fns: dict[str, str]) -> dict[str, int]:
    """Total gesture cost per helper, expanding calls to other helpers.

    Recursive with a cycle guard: a helper in a cycle contributes its own
    gestures once and does not recurse back into itself.
    """
    costs: dict[str, int] = {}

    def cost_of(name: str, seen: frozenset[str]) -> int:
        if name in costs and name not in seen:
            return costs[name]
        body = fns.get(name)
        if body is None or name in seen:
            return 0
        total = _own_gestures(body)
        for call in _CALL_RE.finditer(body):
            callee = call.group(1)
            if callee != name and callee in fns:
                total += cost_of(callee, seen | {name})
        if not seen:
            costs[name] = total
        return total

    for name in fns:
        cost_of(name, frozenset())
    return costs


def _expanded_cost(body: str, costs: dict[str, int]) -> int:
    total = _own_gestures(body)
    for call in _CALL_RE.finditer(body):
        total += costs.get(call.group(1), 0)
    return total


def _shortcuts_used(body: str, fns: dict[str, str]) -> list[str]:
    """WHICH API-seeding helpers `body` reaches, directly or through a helper.

    A boolean here was the first design and it was too blunt to use: 702 of 935
    journeys came back `partial`, because nearly every spec seeds its login over
    the API and rightly so. Lumping "skipped registration" together with
    "skipped creating the part" made the tag unreadable in exactly the audit it
    was built for. The NAMES discriminate: `seedSession` alone is a journey that
    starts after login, which is fine for judging a modelling flow, while
    `createPartViaApi` means the part-creation path itself went unmeasured — and
    that is the one claim this whole script exists to make.
    """
    found: set[str] = set()
    seen: set[str] = set()
    stack = [m.group(1) for m in _CALL_RE.finditer(body)]
    while stack:
        n = stack.pop()
        if n in API_SHORTCUTS:
            found.add(n)
            continue
        if n in seen or n not in fns:
            continue
        seen.add(n)
        stack.extend(m.group(1) for m in _CALL_RE.finditer(fns[n]))
    return sorted(found)


def _helper_table(e2e: Path) -> dict[str, str]:
    """Every function declared in the non-spec helper modules beside the specs."""
    fns: dict[str, str] = {}
    for f in sorted(e2e.glob("*.ts")):
        if f.name.endswith(".spec.ts"):
            continue
        fns.update(_declared_functions(f.read_text()))
    return fns


#: A journey is ONE `test()` block. `test.describe` is excluded deliberately:
#: its body CONTAINS the tests, so counting it too reports every gesture twice
#: and the duplicate row looks like a second, equally expensive journey rather
#: than like an error. Same for `test.step`, which nests inside a test. The
#: modifiers that still denote a single runnable journey are kept.
_TEST_RE = re.compile(
    r"\btest(?:\.(?:only|skip|fixme|fail|slow))?\s*\(\s*[`\"']([^`\"']+)[`\"']",
)


def _callback_body(src: str, after: int) -> str:
    """Body of the callback a `test(...)` declares, from just past its title.

    NOT simply "the next `{`" — that is the destructuring parameter in
    `test("x", async ({ page }) => {`, which closes immediately and reports the
    journey as costing ZERO gestures. Found by this file's own self-test on its
    first run, and it is the silent-zero shape: every number would have been 0
    and the report would have printed happily. Anchor on the arrow instead, and
    fall back to a `function` keyword for the older spelling.
    """
    arrow = src.find("=>", after)
    kw = src.find("function", after)
    # Whichever introducer comes first, within this call's own text.
    stop = min(x for x in (arrow, kw, len(src)) if x >= 0)
    if stop >= len(src):
        return ""
    return _block_at(src, stop)


def _untracked_specs(e2e: Path) -> list[str]:
    """Spec files in `e2e` that git does not track.

    This script walks the FILESYSTEM, so another agent's in-flight scratch specs
    are counted as journeys and the totals move for a reason that has nothing to
    do with the product. Measured 2026-09-11: a live audit agent's five
    `zzflow-*.spec.ts` probes raised the journey count from 650 to 655 in the
    middle of a comparison between two trees, which is precisely the shape of
    error that makes a number untrustworthy — it changed because a colleague was
    working, not because anything shipped.

    The same class as `prettier --check .` walking the filesystem and going red
    on somebody's stray scratch file: a gate is only as honest as its INPUT, and
    "it passed" means nothing until you know what it measured. Warn rather than
    exclude — a scratch spec may be exactly what someone wants to measure — but
    never let the totals shift silently.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", str(e2e)],
            capture_output=True,
            text=True,
            cwd=REPO,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - git absent
        return []
    if out.returncode != 0:
        return []
    return sorted(
        Path(line).name for line in out.stdout.split() if line.endswith(".spec.ts")
    )


def analyse(e2e: Path = E2E) -> list[Journey]:
    shared = _helper_table(e2e)
    journeys: list[Journey] = []
    for spec in sorted(e2e.glob("*.spec.ts")):
        src = spec.read_text()
        # A spec's own helpers shadow nothing; both tables are consulted.
        fns = {**shared, **_declared_functions(src)}
        costs = _resolve_costs(fns)
        for m in _TEST_RE.finditer(src):
            body = _callback_body(src, m.end())
            if not body:
                continue
            journeys.append(
                Journey(
                    spec=spec.name,
                    title=m.group(1),
                    gestures=_expanded_cost(body, costs),
                    skipped=_shortcuts_used(body, fns),
                )
            )
    return journeys


def _self_test() -> int:
    """Prove every rule above can fail. A gate nobody has seen fail is not one."""
    failures: list[str] = []

    def check(label: str, got: object, want: object) -> None:
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    # 1. A drag is ONE gesture, however Playwright spells it. This is the
    #    assertion that stops the metric arguing against direct manipulation.
    drag = """
      await page.mouse.move(10, 10);
      await page.mouse.down();
      await page.mouse.move(10, 50);
      await page.mouse.move(10, 90);
      await page.mouse.up();
    """
    check("drag collapses to one", _own_gestures(drag), 1)

    # Negative control: without the collapse it would read 5 (2 counted moves
    # inside + down + ...). If this ever equals the collapsed count, the rule
    # has stopped doing anything and case 1 passes vacuously.
    naive = len(_ACTION_RE.findall(drag))
    if naive <= 1:
        failures.append(f"drag negative control is vacuous: naive={naive}")

    # 2. Aiming is free; committing is not.
    check("bare move is free", _own_gestures("await page.mouse.move(1, 2);"), 0)
    check("click commits", _own_gestures("await page.mouse.click(1, 2);"), 1)

    # 3. Helper expansion. Unexpanded, this journey reads 1 instead of 3.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "support.ts").write_text(
            "export async function enterSketch(page) {\n"
            "  await page.getByTestId('new-sketch').click();\n"
            "  await page.getByTestId('plane-XY').click();\n"
            "}\n"
            "export async function seedSession(page) { return 1; }\n"
        )
        (d / "demo.spec.ts").write_text(
            "test('draws', async ({ page }) => {\n"
            "  await enterSketch(page);\n"
            "  await page.getByTestId('line').click();\n"
            "});\n"
            "test('seeded', async ({ page }) => {\n"
            "  await seedSession(page);\n"
            "  await page.getByTestId('line').click();\n"
            "});\n"
        )
        got = {j["title"]: j for j in analyse(d)}
        check("helper cost folds into caller", got["draws"]["gestures"], 3)
        check("end-to-end journey skips nothing", got["draws"]["skipped"], [])
        check(
            "API-seeded journey names what it skipped",
            got["seeded"]["skipped"],
            ["seedSession"],
        )

    # 3b. A TypeScript object-literal parameter type must not be mistaken for
    #     the function body. The shape that produced a silent 0 on the real
    #     suite's most important journey.
    typed = {
        "run": "async function run(\n  page: Page,\n  s1: { x: number; y: number },\n"
        "): Promise<void> {\n  await page.getByTestId('a').click();\n"
        "  await page.getByTestId('b').click();\n}\n"
    }
    decls = _declared_functions(typed["run"])
    check("typed param does not swallow the body", _resolve_costs(decls).get("run"), 2)
    # Negative control: the naive "first brace after the name" reading, which is
    # what shipped, must give a DIFFERENT (wrong) answer — otherwise this case
    # passes whether or not the fix is present.
    naive_decl = _FN_DECL_RE.search(typed["run"])
    assert naive_decl is not None, "the fixture must contain a declaration"
    naive_body = _block_at(typed["run"], naive_decl.end())
    if _own_gestures(naive_body) == 2:
        failures.append(
            "typed-param negative control is vacuous: naive reading also gives 2"
        )

    # 3c. `test.describe` must not be counted as a journey of its own — its
    #     body holds the tests, so counting both doubles every gesture.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "nested.spec.ts").write_text(
            "test.describe('group', () => {\n"
            "  test('inner', async ({ page }) => {\n"
            "    await page.getByTestId('a').click();\n"
            "  });\n"
            "});\n"
        )
        rows = analyse(d)
        check("describe is not a journey", [r["title"] for r in rows], ["inner"])

    # 4. The extractor must still account for the REAL suite. If brace matching
    #    or the test regex silently stops finding blocks, every number here goes
    #    quietly to zero and the report still prints — the failure shape this
    #    repo has shipped five times. Demand a second, independently derived
    #    count and refuse when the two disagree beyond a stated margin.
    if E2E.is_dir():
        journeys = analyse()
        if len(journeys) < 100:
            failures.append(f"only {len(journeys)} journeys found in the real suite")
        walked = sum(j["gestures"] for j in journeys)
        literal = sum(_own_gestures(f.read_text()) for f in E2E.glob("*.spec.ts"))
        # Expansion means walked >= literal-inside-tests; it must not COLLAPSE.
        if walked < literal:
            failures.append(
                f"expanded total {walked} is below the literal spec total {literal} — "
                "helper expansion or block extraction has stopped working"
            )

    for f in failures:
        print(f"FAIL  {f}")
    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--journey", help="filter by spec name or test title (regex)")
    ap.add_argument("--top", type=int, default=25, help="how many rows to print")
    ap.add_argument("--self-test", action="store_true", help="prove it can fail")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    journeys = analyse()
    if args.journey:
        pat = re.compile(args.journey, re.I)
        journeys = [
            j for j in journeys if pat.search(j["spec"]) or pat.search(j["title"])
        ]

    journeys.sort(key=lambda j: -j["gestures"])

    if args.json:
        print(json.dumps({"journeys": journeys}, indent=2))
        return 0

    stray = _untracked_specs(E2E)
    if stray:
        print(
            f"::warning:: {len(stray)} UNTRACKED spec file(s) in apps/web/e2e are "
            "being counted as journeys:\n  " + "\n  ".join(stray) + "\n"
            "They are somebody's in-flight work, not the committed product. Totals "
            "below include them — do not compare this run against another tree "
            "until they are gone.\n"
        )

    full = [j for j in journeys if not j["skipped"]]
    skipped_part = [j for j in journeys if "createPartViaApi" in j["skipped"]]
    print("GESTURES PER JOURNEY — what the task costs the hand.\n")
    for j in journeys[: args.top]:
        skipped = ", ".join(j["skipped"]) or "nothing"
        print(f"{j['gestures']:5d}  {j['spec']}  ::  {j['title'][:56]}")
        print(f"        skipped over the API: {skipped}")
    print(
        f"\n{len(journeys)} journeys. {len(full)} drive everything through the UI; "
        f"{len(skipped_part)} never create a part through it at all."
    )
    print(
        "\nREAD THE SPEC BEFORE BELIEVING A ROW. A high count is often a "
        "MEASUREMENT PROBE\n(a scan of 18 points along an edge) rather than an "
        "expensive journey — this is a\nsearch-ordering tool, and triage is the "
        "step that turns it into evidence.\nA drop in any number is a QUESTION, "
        "not an achievement: pair it with the diff\nthat shortened the path, or "
        "it was the spec that changed, not the product."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

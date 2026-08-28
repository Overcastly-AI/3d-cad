#!/usr/bin/env python3
"""A Tailwind utility this theme cannot generate is SILENT, and measures zero.

Why this exists
---------------
``packages/design`` *replaces* Tailwind's scales with the token scales on
purpose — only token values may exist in the DOM theme. The cost of that
decision is a failure mode with no signal at all: when a source file asks for a
step the scale does not have, Tailwind emits **no rule**. No warning, no build
error, no fallback. ``w-32`` on a progress bed became ``width: <nothing>``, the
element resolved to **zero width**, the DOM looked perfect, every attribute was
right, and Playwright reported the ``role="progressbar"`` as *hidden*
(2026-08-28, ``packages/design/src/primitives/ProgressTrack.tsx``; the scale is
closed at ``12``).

It was the third zero-area defect of that week, each with a different cause — an
SVG stroke ``getBoundingClientRect`` ignores, an ``sr-only`` element clipped out
of frame, and this. All three presented identically as "the control is there and
cannot be touched". This is the only one of the three a static check can catch
cheaply, so this is that check.

What was already here, and what was not
---------------------------------------
``apps/web/src/test/tailwindUtilities.test.ts`` compiles candidate classes
through the REAL Tailwind and is authoritative about whether a rule is emitted.
It is not replaced and must not be: when the two disagree, it is right. But it
has two gaps this closes.

1. **It runs in ``just test``, not ``just lint``.** The ProgressTrack defect was
   found in a browser, by hand, before anybody ran the vitest suite. A gate that
   fires 40 ms into ``just lint`` — which every agent runs before committing —
   catches it while the class is still on screen.
2. **Interpolated template literals are invisible to it.** Its literal regex is
   ``` `([^`\\$\n]*)` ```: a backtick literal containing ``${`` does not match at
   all, so *every* class in it is unscanned. Measured on the tree at
   ``fe58fd9``: **48 such literals across 19 files** carry class-shaped tokens.
   This scanner splits a template at its holes and reads the literal chunks,
   dropping only the tokens that actually touch a hole (``w-${n}`` is a class
   name assembled at runtime and is honestly unknowable — see the blind spot
   below).

Scope — deliberately narrow, because a gate that cries wolf gets disabled
------------------------------------------------------------------------
Tailwind's utility surface is large; almost all of it fails loudly or is not
closed by this preset. Only two shapes fail *silently*, and only those are
covered:

* **Spacing-keyed families** (``w- h- p* m* gap- space-* inset* top/right/
  bottom/left- size- min-/max-* translate-* scroll-m*/scroll-p* indent- basis-``)
  — the preset replaces ``theme.spacing``, so a step outside it emits nothing.
* **Families whose whole scale the preset replaces** — ``text-`` (fontSize),
  ``rounded*`` (borderRadius), ``duration-`` (transitionDuration). Every key in
  those is a NAME (``sm``, ``fast``), so any numeric ``text-14`` is dead.

Out of scope, each for a reason:

* ``z-`` — the preset *extends* ``zIndex`` rather than replacing it, so
  Tailwind's own ``0 10 20 30 40 50 auto`` still resolve. There is no closed
  scale to check against without transcribing Tailwind's defaults, which is the
  duplication this file exists to avoid.
* ``leading-`` — measured: it reads ``lineHeight``, its own untouched default
  scale (``leading-7`` resolves while ``p-7`` does not). Not spacing-keyed.
* Colours, fonts, ``opacity``, ``grid-*``, ``order-*``, flex/display/position
  keywords — either not closed by the preset, or loud when wrong (a missing
  background is visible; a missing width is not).
* **Named keys** (``h-band``, ``bottom-hud-lane``, ``max-w-sheet``). A single
  token like ``top-toolbar`` is indistinguishable from a ``data-testid`` by
  shape, so treating it as a class produces false positives on prose. The
  curated vocabulary fixture in ``tailwindUtilities.test.ts`` covers those, with
  a real compiler behind it.

Value shapes, stated so the boundary is not a surprise:

* ``w-32``, ``p-1.5``, ``w-px`` — CHECKED (a numeric step, or the hairline).
* ``w-[3.5rem]``, ``w-1/2``, ``w-full``, ``h-auto``, ``max-w-sheet`` — never
  flagged. Arbitrary values are valid by construction; fractions and keywords
  come from Tailwind's own defaults, which this preset leaves alone (measured).
* ``md:w-32``, ``group-hover/tt:w-32``, ``[[data-x=y]_&]:w-32`` — variants are
  stripped at the last top-level ``:`` (brackets respected) and the bare utility
  is checked.
* ``!w-32`` / ``w-32!`` — an ``!important`` marker is stripped from either end.
* ``-mt-32`` — a leading ``-`` is stripped and the KEY is checked. Whether the
  family admits negatives at all (``-p-1`` does not exist) is a different
  defect and is not judged here.

The blind spot, which is real and cannot be closed
--------------------------------------------------
**A class assembled at runtime is invisible to any static check, including this
one.** ``` `w-${n}` ``` , ``clsx("w-" + step)``, a class name arriving from
props or a map value — this scanner drops the token that touches the hole
precisely so it does not guess, and it cannot see the others at all. Tailwind
itself has the same blind spot for the same reason (its content scanner is
regex over source), which is why the house rule is to write whole class names as
literals and select between them — ``x ? "w-12" : "w-6"``, never ``` `w-${x}`
``` . This gate makes that rule cheaper to follow; it does not enforce it.

How the valid keys are derived
------------------------------
From ``packages/design/src/tokens.ts`` and ``packages/design/src/
tailwind-preset.ts``, by parsing them — never from a transcribed list, which
would be a second copy of the scale and would go stale the first time somebody
adds a step. The preset's top-level ``theme`` block says which token constant
backs which Tailwind theme key (``spacing: mapPx(spacing)``), and its ``extend``
block contributes the named keys (``width: { carriage: ... }``). The FAMILY ->
theme-key table below is Tailwind's own plugin semantics, not our scale, and it
was verified against the real compiler rather than assumed (see the note on
``SPACING_FAMILIES``).

Two independent derivations of every object's keys must agree, or the script
REFUSES rather than guessing — a character-level scanner that understands
strings and comments, and a line-level regex that counts braces. They agree on a
flat object literal and diverge the moment the file's shape changes in a way
nobody taught this parser, which is exactly when a silent wrong answer would be
most expensive.

Usage
-----
    python3 scripts/check-tailwind-scale.py               # gate the repo
    python3 scripts/check-tailwind-scale.py --verbose     # + the derived scales
    python3 scripts/check-tailwind-scale.py --self-test   # prove it can fail

Exit codes: 0 clean, 1 findings (or a failed self-test), 2 refusal (the tree
does not look the way this parser understands, or too few files were scanned —
``all([])`` is True and a gate that scans nothing passes vacuously).
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Floors. A gate that scans nothing passes; five gates in this repo have shipped
# that way. These are deliberately well under the real numbers (at fe58fd9: 430
# files, 2578 candidates) so ordinary growth never trips them, and a scanner
# that silently stops finding sources does.
# ---------------------------------------------------------------------------
MIN_FILES = 150
MIN_CANDIDATES = 400

# ---------------------------------------------------------------------------
# Tailwind v3 core-plugin semantics: which theme scale a utility family reads.
# This is the TOOL's table, not our token scale — the keys come from the preset.
# Verified against tailwindcss 3.4.19 by compiling every family x value pair and
# reading which rules were emitted; that measurement is what removed `leading-`
# (lineHeight, not spacing) and `z-` (extended, not replaced) from the list, and
# what confirmed that `max-w-`/`max-h-` DO spread spacing in 3.4.
# ---------------------------------------------------------------------------
SPACING_FAMILIES: dict[str, str] = {
    # padding
    "p": "padding",
    "px": "padding",
    "py": "padding",
    "pt": "padding",
    "pr": "padding",
    "pb": "padding",
    "pl": "padding",
    "ps": "padding",
    "pe": "padding",
    # margin
    "m": "margin",
    "mx": "margin",
    "my": "margin",
    "mt": "margin",
    "mr": "margin",
    "mb": "margin",
    "ml": "margin",
    "ms": "margin",
    "me": "margin",
    # gaps
    "gap": "gap",
    "gap-x": "gap",
    "gap-y": "gap",
    "space-x": "space",
    "space-y": "space",
    # box size
    "w": "width",
    "h": "height",
    "size": "size",
    "min-w": "minWidth",
    "min-h": "minHeight",
    "max-w": "maxWidth",
    "max-h": "maxHeight",
    # position
    "inset": "inset",
    "inset-x": "inset",
    "inset-y": "inset",
    "top": "inset",
    "right": "inset",
    "bottom": "inset",
    "left": "inset",
    "start": "inset",
    "end": "inset",
    # transform / flex / scroll / text-indent
    "translate-x": "translate",
    "translate-y": "translate",
    "basis": "flexBasis",
    "indent": "textIndent",
    "scroll-m": "scrollMargin",
    "scroll-mx": "scrollMargin",
    "scroll-my": "scrollMargin",
    "scroll-mt": "scrollMargin",
    "scroll-mr": "scrollMargin",
    "scroll-mb": "scrollMargin",
    "scroll-ml": "scrollMargin",
    "scroll-p": "scrollPadding",
    "scroll-px": "scrollPadding",
    "scroll-py": "scrollPadding",
    "scroll-pt": "scrollPadding",
    "scroll-pr": "scrollPadding",
    "scroll-pb": "scrollPadding",
    "scroll-pl": "scrollPadding",
}

# Families whose ENTIRE scale the preset replaces at the top level of `theme`.
# Their valid keys are the token constant's keys plus anything `extend` adds —
# every one of which is a name today, so a numeric step in these is always dead.
# Covered only while the preset really does replace them: if one moves into
# `extend`, Tailwind's defaults come back and flagging would be crying wolf, so
# the family is dropped from coverage instead (reported under --verbose).
REPLACED_FAMILIES: dict[str, str] = {
    "text": "fontSize",
    "duration": "transitionDuration",
    "rounded": "borderRadius",
    "rounded-t": "borderRadius",
    "rounded-r": "borderRadius",
    "rounded-b": "borderRadius",
    "rounded-l": "borderRadius",
    "rounded-tl": "borderRadius",
    "rounded-tr": "borderRadius",
    "rounded-br": "borderRadius",
    "rounded-bl": "borderRadius",
    "rounded-s": "borderRadius",
    "rounded-e": "borderRadius",
    "rounded-ss": "borderRadius",
    "rounded-se": "borderRadius",
    "rounded-es": "borderRadius",
    "rounded-ee": "borderRadius",
}

# The only value shapes that are unambiguously a scale step. Everything else —
# fractions, keywords, arbitrary values, named tokens — is out of scope above.
NUMERIC_VALUE = re.compile(r"^\d+(?:\.\d+)?$")
HAIRLINE_VALUE = "px"

# Sources whose STRING LITERALS deliberately name classes that must not
# resolve, so scanning them would report their fixtures as defects.
#
# The general opt-out is this marker anywhere in the file, so a future fixture
# needs no edit here:
FIXTURE_MARKER = "check-tailwind-scale: fixture"
# ...and these two are the sibling guard's own files, which predate the marker
# and live in another agent's territory. The script REFUSES if a listed path
# stops existing, so this cannot rot into a silent hole.
FIXTURE_PATHS: tuple[str, ...] = (
    "apps/web/src/test/tailwindUtilities.ts",
    "apps/web/src/test/tailwindUtilities.test.ts",
)


class Refusal(Exception):
    """The tree does not look the way this parser understands. Do not guess."""


# ---------------------------------------------------------------------------
# A single source scanner: skips comments, yields string literals, and splits
# template literals at their `${...}` holes.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Literal:
    """A run of literal source text that may carry class names."""

    text: str
    offset: int
    #: the chunk is preceded / followed by a `${...}` hole, so the token
    #: touching that edge may be a fragment of a runtime-assembled class.
    left_open: bool
    right_open: bool


#: A `/` opens a regex literal (rather than dividing) when the previous
#: significant character is one of these. Crude but standard, and the cost of a
#: miss is a junk token that matches no family.
_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%~^<>")


def _significant_before(src: str, i: int) -> str:
    j = i - 1
    while j >= 0 and src[j] in " \t\r\n":
        j -= 1
    return src[j] if j >= 0 else ""


def _skip_string(src: str, i: int, quote: str) -> int:
    """Return the index just past a simple quoted string starting at `i`."""
    i += 1
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == quote or c == "\n":
            return i + 1
        i += 1
    return i


def _skip_hole(src: str, i: int) -> int:
    """Return the index just past a `${ ... }` hole starting at `i` (`$`)."""
    i += 2
    depth = 1
    while i < len(src) and depth > 0:
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        elif c in "\"'":
            i = _skip_string(src, i, c) - 1
        elif c == "`":
            i = _skip_template(src, i)[0] - 1
        i += 1
    return i


def _skip_template(src: str, i: int) -> tuple[int, list[Literal]]:
    """Scan a template literal at `i`; return (end index, literal chunks)."""
    chunks: list[Literal] = []
    i += 1
    start = i
    left_open = False
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "$" and src[i : i + 2] == "${":
            chunks.append(Literal(src[start:i], start, left_open, True))
            i = _skip_hole(src, i)
            start = i
            left_open = True
            continue
        if c == "`":
            chunks.append(Literal(src[start:i], start, left_open, False))
            return i + 1, chunks
        i += 1
    chunks.append(Literal(src[start:i], start, left_open, False))
    return i, chunks


def scan_literals(src: str) -> list[Literal]:
    """Every string/template literal in `src`, comments and regexes skipped."""
    out: list[Literal] = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == "/" and src[i : i + 2] == "//":
            nl = src.find("\n", i)
            i = n if nl < 0 else nl
            continue
        if c == "/" and src[i : i + 2] == "/*":
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if c == "/" and _significant_before(src, i) in _REGEX_PRECEDERS:
            i += 1
            while i < n and src[i] != "\n":
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == "[":
                    while i < n and src[i] != "]" and src[i] != "\n":
                        i += 2 if src[i] == "\\" else 1
                if src[i] == "/":
                    i += 1
                    break
                i += 1
            continue
        if c in "\"'":
            end = _skip_string(src, i, c)
            out.append(Literal(src[i + 1 : end - 1], i + 1, False, False))
            i = end
            continue
        if c == "`":
            end, chunks = _skip_template(src, i)
            out.extend(chunks)
            i = end
            continue
        i += 1
    return out


def literal_tokens(lit: Literal) -> list[tuple[str, int]]:
    """Whitespace-separated tokens of a literal, with their source offsets.

    A token that TOUCHES a `${...}` hole is dropped: ``w-${n}`` is a class
    assembled at runtime, and reporting its ``w-`` fragment as a dead utility
    would be the false positive that gets a gate disabled. This is the blind
    spot named in the module docstring, made explicit rather than guessed at.
    """
    parts: list[tuple[str, int]] = []
    for m in re.finditer(r"\S+", lit.text):
        parts.append((m.group(0), lit.offset + m.start()))
    if not parts:
        return []
    if lit.left_open and not lit.text[:1].isspace():
        parts = parts[1:]
    if parts and lit.right_open and not lit.text[-1:].isspace():
        parts = parts[:-1]
    return parts


# ---------------------------------------------------------------------------
# Utility-name normalisation
# ---------------------------------------------------------------------------


def strip_variants(token: str) -> str:
    """Drop `md:`, `hover:`, `[[data-x=y]_&]:` prefixes and `!` markers."""
    depth = 0
    cut = -1
    for i, c in enumerate(token):
        if c in "[(":
            depth += 1
        elif c in "])":
            depth -= 1
        elif c == ":" and depth == 0:
            cut = i
    bare = token[cut + 1 :] if cut >= 0 else token
    return bare.strip("!")


#: Longest first, so `min-w-12` is `min-w` rather than `min` + `w-12`, and
#: `inset-x-2` is `inset-x` rather than `inset` + `x-2`.
_FAMILIES_BY_LENGTH: list[str] = sorted(
    set(SPACING_FAMILIES) | set(REPLACED_FAMILIES), key=len, reverse=True
)


def split_family(utility: str) -> tuple[str, str] | None:
    """`("min-w", "12")` for `min-w-12`, else None. Longest family wins."""
    bare = utility[1:] if utility.startswith("-") else utility
    for family in _FAMILIES_BY_LENGTH:
        prefix = family + "-"
        if bare.startswith(prefix):
            return family, bare[len(prefix) :]
    return None


def is_scale_step(value: str) -> bool:
    """Only an unambiguous scale step is judged (see the docstring's table)."""
    return value == HAIRLINE_VALUE or NUMERIC_VALUE.match(value) is not None


# ---------------------------------------------------------------------------
# Deriving the scales FROM the preset. Two independent readings must agree.
# ---------------------------------------------------------------------------


def _blank_comments(src: str) -> str:
    """Replace comment bodies with spaces, preserving offsets and newlines."""
    out = list(src)
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == "/" and src[i : i + 2] == "//":
            end = src.find("\n", i)
            end = n if end < 0 else end
            for j in range(i, end):
                out[j] = " "
            i = end
            continue
        if c == "/" and src[i : i + 2] == "/*":
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for j in range(i, end):
                if out[j] != "\n":
                    out[j] = " "
            i = end
            continue
        if c in "\"'":
            i = _skip_string(src, i, c)
            continue
        if c == "`":
            i = _skip_template(src, i)[0]
            continue
        i += 1
    return "".join(out)


def _match_brace(src: str, open_idx: int) -> int:
    """Index of the `}` closing the `{` at `open_idx` (comments blanked)."""
    depth = 0
    i = open_idx
    n = len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            i = _skip_string(src, i, c)
            continue
        if c == "`":
            i = _skip_template(src, i)[0]
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise Refusal(f"unbalanced braces from offset {open_idx}")


_KEY_RE = re.compile(r"""\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z_$][\w$-]*))\s*:""")


def object_entries(body: str) -> list[tuple[str, str]]:
    """Top-level `key: value` pairs of an object literal body (no braces).

    Reading A: a character scanner that understands strings, templates and
    nesting.
    """
    entries: list[tuple[str, str]] = []
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c in " \t\r\n,":
            i += 1
            continue
        m = _KEY_RE.match(body, i)
        if m is None:
            # Not a key at this position (spread, comment residue): step past it
            # without pretending to understand — the cross-check will notice if
            # this loses an entry.
            i += 1
            continue
        key = m.group(1) or m.group(2) or m.group(3)
        j = m.end()
        depth = 0
        start = j
        while j < n:
            d = body[j]
            if d in "\"'":
                j = _skip_string(body, j, d)
                continue
            if d == "`":
                j = _skip_template(body, j)[0]
                continue
            if d in "{[(":
                depth += 1
            elif d in "}])":
                depth -= 1
            elif d == "," and depth == 0:
                break
            j += 1
        entries.append((key, body[start:j].strip()))
        i = j + 1
    return entries


_NESTED_GROUP = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]|\([^()]*\)")
_KEY_AT_TOP = re.compile(
    r"""(?:^|[,{])\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z_$][\w$-]*))\s*:""", re.M
)


def object_keys_flattened(body: str) -> list[str]:
    """Reading B, derived by a different mechanism on purpose: blank out the
    innermost bracket groups until none are left, then match keys that follow a
    `,` or a line start.

    It agrees with reading A on the object shapes this repo writes and diverges
    the moment one changes in a way neither parser was taught — for instance a
    STRING value containing `, key:`, which A skips as a string and B reads as
    another entry. That disagreement is the point: it makes an unknown shape
    loud instead of silently changing the answer.
    """
    flat = body
    while True:
        blanked = _NESTED_GROUP.sub(lambda m: " " * len(m.group(0)), flat)
        if blanked == flat:
            break
        flat = blanked
    return [m.group(1) or m.group(2) or m.group(3) for m in _KEY_AT_TOP.finditer(flat)]


def agreed_keys(body: str, what: str) -> list[str]:
    """Keys of an object literal, or a REFUSAL if the two readings disagree."""
    a = [k for k, _ in object_entries(body)]
    b = object_keys_flattened(body)
    if a != b:
        raise Refusal(
            f"two readings of {what} disagree "
            f"(scanner={a!r}, lines={b!r}); refusing to guess which is right"
        )
    return a


def declared_object(src: str, name: str) -> str | None:
    """Body of `export const <name> = { ... }`, comments blanked."""
    m = re.search(rf"export\s+const\s+{re.escape(name)}\s*(?::[^=]*)?=\s*\{{", src)
    if m is None:
        return None
    open_idx = src.index("{", m.end() - 1)
    return src[open_idx + 1 : _match_brace(src, open_idx)]


@dataclass(frozen=True)
class Theme:
    """The parts of the preset this gate reasons about."""

    #: Tailwind theme key -> keys of the token constant that REPLACES it.
    replaced: dict[str, frozenset[str]]
    #: Tailwind theme key -> keys the preset's `extend` block adds.
    extended: dict[str, frozenset[str]]


def derive_theme(tokens_src: str, preset_src: str) -> Theme:
    tokens = _blank_comments(tokens_src)
    preset = _blank_comments(preset_src)

    preset_body = declared_object(preset, "loftPreset")
    if preset_body is None:
        raise Refusal("no `export const loftPreset = {` in the preset")
    theme_value = dict(object_entries(preset_body)).get("theme")
    if theme_value is None or not theme_value.startswith("{"):
        raise Refusal("the preset's `theme` is not an object literal")
    theme_body = theme_value[1 : _match_brace(theme_value, 0)]

    replaced: dict[str, frozenset[str]] = {}
    extended: dict[str, frozenset[str]] = {}
    for key, value in object_entries(theme_body):
        if key == "extend":
            if not value.startswith("{"):
                raise Refusal("the preset's `theme.extend` is not an object literal")
            extend_body = value[1 : _match_brace(value, 0)]
            for ext_key, ext_value in object_entries(extend_body):
                if ext_value.startswith("{"):
                    inner = ext_value[1 : _match_brace(ext_value, 0)]
                    extended[ext_key] = frozenset(
                        agreed_keys(inner, f"theme.extend.{ext_key}")
                    )
            continue
        if value.startswith("{"):
            # A literal object at the top level of `theme` replaces the scale
            # with exactly its own keys.
            inner = value[1 : _match_brace(value, 0)]
            replaced[key] = frozenset(agreed_keys(inner, f"theme.{key}"))
            continue
        # `spacing: mapPx(spacing)` — the token constant backing this theme key
        # is the identifier inside the call. Take the LAST identifier so the
        # wrapper (`mapPx`, `ms`) is never mistaken for the scale.
        idents = re.findall(r"[A-Za-z_$][\w$]*", value)
        for ident in reversed(idents):
            body = declared_object(tokens, ident)
            if body is not None:
                replaced[key] = frozenset(agreed_keys(body, f"tokens.{ident}"))
                break
    if "spacing" not in replaced:
        raise Refusal(
            "the preset no longer replaces `theme.spacing` from a token constant; "
            "this gate's whole premise (a CLOSED spacing scale) is gone"
        )
    return Theme(replaced=replaced, extended=extended)


def valid_keys(theme: Theme, family: str) -> frozenset[str] | None:
    """Keys `family-<key>` can resolve, or None when the family is not covered."""
    if family in SPACING_FAMILIES:
        theme_key = SPACING_FAMILIES[family]
        return theme.replaced["spacing"] | theme.extended.get(theme_key, frozenset())
    theme_key = REPLACED_FAMILIES[family]
    scale = theme.replaced.get(theme_key)
    if scale is None:
        # Not replaced after all -> Tailwind's defaults apply and we must not
        # flag. Dropping the family is the anti-cry-wolf direction of this gate.
        return None
    return scale | theme.extended.get(theme_key, frozenset())


# ---------------------------------------------------------------------------
# Scanning the sources Tailwind itself scans
# ---------------------------------------------------------------------------

_BRACE_GLOB = re.compile(r"\{([^{}]*)\}")


def expand_braces(pattern: str) -> list[str]:
    m = _BRACE_GLOB.search(pattern)
    if m is None:
        return [pattern]
    out: list[str] = []
    for option in m.group(1).split(","):
        out.extend(
            expand_braces(pattern[: m.start()] + option + pattern[m.end() :]),
        )
    return out


def content_globs(config_src: str) -> list[str]:
    """The `content` globs of a Tailwind config — derived, never transcribed, so
    a new scanned root is covered the day it is added."""
    src = _blank_comments(config_src)
    m = re.search(r"\bcontent\s*:\s*\[", src)
    if m is None:
        raise Refusal("no `content: [` array in the Tailwind config")
    end = src.index("]", m.end() - 1)
    return [lit.text for lit in scan_literals(src[m.end() : end])]


def scanned_files(config_path: Path) -> list[Path]:
    base = config_path.parent
    out: list[Path] = []
    seen: set[Path] = set()
    for glob in content_globs(config_path.read_text(encoding="utf-8")):
        for expanded in expand_braces(glob):
            cleaned = expanded[2:] if expanded.startswith("./") else expanded
            root = base
            while cleaned.startswith("../"):
                root = root.parent
                cleaned = cleaned[3:]
            for path in sorted(root.glob(cleaned)):
                if path.is_file() and path not in seen:
                    seen.add(path)
                    out.append(path)
    return out


@dataclass(frozen=True)
class Finding:
    utility: str
    path: str
    line: int
    valid: str


def _line_of(starts: list[int], offset: int) -> int:
    """1-based line number for a byte offset (`starts` holds line-2..N starts)."""
    return bisect_right(starts, offset) + 1


def check_tree(
    root: Path,
    config_rel: str = "apps/web/tailwind.config.ts",
    min_files: int = MIN_FILES,
    min_candidates: int = MIN_CANDIDATES,
    theme_override: Theme | None = None,
) -> tuple[list[Finding], int, int, Theme]:
    """Scan `root` and return (findings, files scanned, candidates judged)."""
    design = root / "packages/design/src"
    theme = theme_override or derive_theme(
        (design / "tokens.ts").read_text(encoding="utf-8"),
        (design / "tailwind-preset.ts").read_text(encoding="utf-8"),
    )

    fixtures: set[Path] = set()
    for rel in FIXTURE_PATHS:
        path = root / rel
        if not path.exists():
            raise Refusal(
                f"fixture allow-list names a path that no longer exists: {rel}. "
                "Remove the entry (or fix the path) — a stale allow-list is a "
                "silent hole in this gate."
            )
        fixtures.add(path)

    findings: list[Finding] = []
    files = 0
    candidates = 0
    for path in scanned_files(root / config_rel):
        if path.suffix not in (".ts", ".tsx", ".html"):
            continue
        src = path.read_text(encoding="utf-8")
        files += 1
        if path in fixtures or FIXTURE_MARKER in src:
            continue
        starts = [m.start() + 1 for m in re.finditer("\n", src)]
        for lit in scan_literals(src):
            for token, offset in literal_tokens(lit):
                split = split_family(strip_variants(token))
                if split is None:
                    continue
                family, value = split
                if not is_scale_step(value):
                    continue
                keys = valid_keys(theme, family)
                if keys is None:
                    continue
                candidates += 1
                if value not in keys:
                    findings.append(
                        Finding(
                            utility=strip_variants(token),
                            path=str(path.relative_to(root)),
                            line=_line_of(starts, offset),
                            valid=" ".join(sorted(keys, key=_scale_sort)),
                        )
                    )
    if files < min_files:
        raise Refusal(
            f"scanned {files} files, floor is {min_files} — a gate that scans "
            "nothing passes vacuously. Check the config's `content` globs."
        )
    if candidates < min_candidates:
        raise Refusal(
            f"judged {candidates} utilities, floor is {min_candidates} — the "
            "harvest found almost nothing, which means the scanner broke, not "
            "that the sources are clean."
        )
    return findings, files, candidates, theme


def _scale_sort(key: str) -> tuple[int, float, str]:
    if NUMERIC_VALUE.match(key):
        return (1, float(key), "")
    return (0, 0.0, key)


# ---------------------------------------------------------------------------
# Self-test: a fixture that reproduces the REAL defect, a count floor, and two
# negative controls — one per direction, because a guard written against one
# failure encodes that failure's direction (CLAUDE.md, 2026-08-11).
# ---------------------------------------------------------------------------

_FIXTURE_TOKENS = """
export const fontSize = { xs: 11, sm: 12, base: 13 } as const;

/** Closed on purpose — the loaded gun this gate exists for. `32` is not here. */
export const spacing = {
  "0": 0,
  px: 1,
  "0.5": 2,
  "1": 4,
  "1.5": 6,
  "2": 8,
  "2.5": 10,
  "3": 12,
  "12": 48,
} as const;

export const radius = { none: 0, sm: 2 } as const;
export const duration = { fast: 120, base: 200 } as const;
export const layout = { bedWidth: 96 } as const;
"""

_FIXTURE_PRESET = """
import type { Config } from "tailwindcss";
import { duration, fontSize, layout, radius, spacing } from "./tokens";

const px = (n: number): string => `${n}px`;
const mapPx = <K extends string>(s: Record<K, number>): Record<K, string> =>
  Object.fromEntries(Object.entries<number>(s).map(([k, v]) => [k, px(v)])) as
    Record<K, string>;
const ms = mapPx;

export const loftPreset = {
  theme: {
    fontSize: mapPx(fontSize),
    spacing: mapPx(spacing),
    borderRadius: mapPx(radius),
    transitionDuration: ms(duration),
    extend: {
      minWidth: {
        progress: px(layout.bedWidth),
      },
    },
  },
} satisfies Partial<Config>;
"""

_FIXTURE_CONFIG = """
import { loftPreset } from "@loft/design/tailwind-preset";
export default {
  presets: [loftPreset],
  content: ["./index.html", "./src/**/*.{ts,tsx}",
            "../../packages/design/src/**/*.{ts,tsx}"],
};
"""

#: The real defect, byte-for-byte in shape: a bed sized with a step the closed
#: scale does not have, sitting in an otherwise perfectly ordinary class list.
_FIXTURE_BAD = """
export const Bed = () => (
  <div className="relative h-track w-32 grow overflow-hidden bg-hairline" />
);
"""

#: Everything here must stay silent. `w-12` is in the scale, `w-[3.5rem]` is an
#: arbitrary value, and the rest are the variant / negative / important /
#: fraction / keyword / named-token shapes the docstring promises not to flag.
_FIXTURE_GOOD = """
export const Fine = () => (
  <div
    className={cx(
      "w-12 w-[3.5rem] p-1.5 gap-2.5 h-px -mt-2 !py-2 max-w-1/2",
      "md:hover:w-12 group-hover/tt:p-3 [[data-band-tier=icon]_&]:gap-1",
      "h-full w-auto min-w-progress text-sm rounded-sm duration-fast",
    )}
    data-testid="top-toolbar"
    aria-label="press left-arrow then top-left"
  />
);
"""

#: The hole the sibling vitest guard cannot see: a template literal with an
#: interpolation. Every class in it is invisible to a regex that requires no
#: `$` between the backticks.
_FIXTURE_INTERP = """
export const Row = ({ active }: { active: boolean }) => (
  <div className={`flex ${active ? "bg-brass" : ""} w-32 p-7`} />
);
"""

#: A class ASSEMBLED at runtime. Unknowable by construction, and reporting the
#: `w-` fragment would be the false positive that gets a gate switched off.
_FIXTURE_PARTIAL = """
export const Step = ({ n, k }: { n: string; k: string }) => (
  <div className={`w-${n} p-${k} gap-2`} />
);
"""

_FIXTURE_OPTOUT = """
// check-tailwind-scale: fixture
export const dead = ["w-52", "p-7", "max-h-64"];
"""

_FIXTURE_HTML = """<!doctype html>
<html><body><div id="root" class="w-32 h-px"></div></body></html>
"""

_FIXTURE_FILLER = 'export const c{n} = "p-2 gap-1.5 mt-3 w-12";\n'


def _write_fixture(root: Path, *, filler: int = 12) -> None:
    design = root / "packages/design/src"
    web = root / "apps/web/src"
    design.mkdir(parents=True)
    web.mkdir(parents=True)
    (design / "tokens.ts").write_text(_FIXTURE_TOKENS, encoding="utf-8")
    (design / "tailwind-preset.ts").write_text(_FIXTURE_PRESET, encoding="utf-8")
    (root / "apps/web/tailwind.config.ts").write_text(_FIXTURE_CONFIG, encoding="utf-8")
    (root / "apps/web/index.html").write_text(_FIXTURE_HTML, encoding="utf-8")
    (web / "Bad.tsx").write_text(_FIXTURE_BAD, encoding="utf-8")
    (web / "Good.tsx").write_text(_FIXTURE_GOOD, encoding="utf-8")
    (web / "Interp.tsx").write_text(_FIXTURE_INTERP, encoding="utf-8")
    (web / "Partial.tsx").write_text(_FIXTURE_PARTIAL, encoding="utf-8")
    (design / "Optout.ts").write_text(_FIXTURE_OPTOUT, encoding="utf-8")
    for i in range(filler):
        (web / f"Filler{i}.ts").write_text(
            _FIXTURE_FILLER.replace("{n}", str(i)), encoding="utf-8"
        )
    for rel in FIXTURE_PATHS:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('export const x = "w-52";\n', encoding="utf-8")


def _fixture_findings(root: Path, theme: Theme | None = None) -> set[tuple[str, str]]:
    findings, _, _, _ = check_tree(
        root, min_files=8, min_candidates=10, theme_override=theme
    )
    return {(f.path, f.utility) for f in findings}


#: Reading the scale as "whatever Tailwind ships" — the naive derivation the
#: brief for this gate warns about, and the one an author reaches for when the
#: preset is hard to parse. `w-32` and `p-7` are both in Tailwind's defaults.
def _naive_default_theme() -> Theme:
    steps = {"0", "px", "0.5", "1", "1.5", "2", "2.5", "3", "3.5"}
    steps |= {str(n) for n in (4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 20, 24)}
    steps |= {str(n) for n in (28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 72, 80, 96)}
    return Theme(replaced={"spacing": frozenset(steps)}, extended={})


#: The SYMMETRIC naive reading: "it's a 4px grid, so integers up to 12". Fires
#: on the half-steps and the hairline the dense chrome actually uses — the
#: cries-wolf direction, which a guard written against the first mistake alone
#: would sit out.
def _naive_grid_theme() -> Theme:
    return Theme(
        replaced={
            "spacing": frozenset({str(n) for n in (0, 1, 2, 3, 4, 5, 6, 8, 10, 12)})
        },
        extended={},
    )


def self_test() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    tmp = Path(tempfile.mkdtemp(prefix="tw-scale-selftest-"))
    try:
        root = tmp / "repo"
        _write_fixture(root)

        # --- derivation -------------------------------------------------
        theme = derive_theme(
            (root / "packages/design/src/tokens.ts").read_text(encoding="utf-8"),
            (root / "packages/design/src/tailwind-preset.ts").read_text(
                encoding="utf-8"
            ),
        )
        expected_spacing = {"0", "px", "0.5", "1", "1.5", "2", "2.5", "3", "12"}
        record(
            "derives the closed spacing scale from the preset",
            set(theme.replaced["spacing"]) == expected_spacing,
            f"got {sorted(theme.replaced['spacing'])}",
        )
        record(
            "derives the extend block's named keys",
            theme.extended.get("minWidth") == frozenset({"progress"}),
            f"got {theme.extended.get('minWidth')}",
        )
        record(
            "derives the replaced scales (fontSize/borderRadius/duration)",
            {"fontSize", "borderRadius", "transitionDuration"}.issubset(theme.replaced),
            f"got {sorted(theme.replaced)}",
        )

        # --- the real defect, and the shapes that must stay silent ------
        found = _fixture_findings(root)
        record(
            "catches the REAL defect (w-32 against a scale closed at 12)",
            ("apps/web/src/Bad.tsx", "w-32") in found,
            f"got {sorted(found)}",
        )
        record(
            "catches it inside an INTERPOLATED template literal",
            {("apps/web/src/Interp.tsx", "w-32"), ("apps/web/src/Interp.tsx", "p-7")}
            <= found,
            f"got {sorted(found)}",
        )
        record(
            "catches it in the scanned index.html",
            ("apps/web/index.html", "w-32") in found,
            f"got {sorted(found)}",
        )
        record(
            "does NOT flag w-12, w-[3.5rem], variants, negatives, !, fractions",
            not any(path.endswith("Good.tsx") for path, _ in found),
            f"got {sorted(f for f in found if f[0].endswith('Good.tsx'))}",
        )
        record(
            "does NOT flag a class assembled at runtime (`w-${n}`)",
            not any(path.endswith("Partial.tsx") for path, _ in found),
            f"got {sorted(f for f in found if f[0].endswith('Partial.tsx'))}",
        )
        record(
            "honours the fixture opt-out marker and the allow-list",
            not any(
                path.endswith(("Optout.ts", "tailwindUtilities.ts"))
                for path, _ in found
            ),
            f"got {sorted(found)}",
        )
        record(
            "reports exactly the four expected findings, nothing else",
            found
            == {
                ("apps/web/src/Bad.tsx", "w-32"),
                ("apps/web/src/Interp.tsx", "w-32"),
                ("apps/web/src/Interp.tsx", "p-7"),
                ("apps/web/index.html", "w-32"),
            },
            f"got {sorted(found)}",
        )

        # --- the vacuity floors -----------------------------------------
        refused = False
        try:
            check_tree(root, min_files=500, min_candidates=10)
        except Refusal:
            refused = True
        record("REFUSES when it scanned fewer files than the floor", refused)

        refused = False
        try:
            check_tree(root, min_files=8, min_candidates=10_000)
        except Refusal:
            refused = True
        record("REFUSES when it judged fewer utilities than the floor", refused)

        # --- refusal rather than a guess --------------------------------
        broken = tmp / "broken"
        _write_fixture(broken)
        tokens_path = broken / "packages/design/src/tokens.ts"
        tokens_path.write_text(
            tokens_path.read_text(encoding="utf-8").replace(
                "export const spacing", "export const spacingScale"
            ),
            encoding="utf-8",
        )
        refused = False
        try:
            derive_theme(
                tokens_path.read_text(encoding="utf-8"),
                (broken / "packages/design/src/tailwind-preset.ts").read_text(
                    encoding="utf-8"
                ),
            )
        except Refusal:
            refused = True
        record("REFUSES when the preset stops replacing theme.spacing", refused)

        # A shape neither reading was taught — a STRING value that contains
        # `, key:` — is read as one entry by the scanner and two by the
        # flattener. The tool must say so rather than pick one.
        disagree = tmp / "disagree"
        _write_fixture(disagree)
        tokens_path = disagree / "packages/design/src/tokens.ts"
        tokens_path.write_text(
            tokens_path.read_text(encoding="utf-8").replace(
                '  "12": 48,', '  "12": 48,\n  note: "grid, step: 4px",'
            ),
            encoding="utf-8",
        )
        refused = False
        try:
            derive_theme(
                tokens_path.read_text(encoding="utf-8"),
                (disagree / "packages/design/src/tailwind-preset.ts").read_text(
                    encoding="utf-8"
                ),
            )
        except Refusal:
            refused = True
        record("REFUSES when its two readings of a scale disagree", refused)

        # --- NEGATIVE CONTROLS ------------------------------------------
        # Reverting the derivation must break the self-test. Asserting the exit
        # code alone would have passed all along, so each control asserts the
        # SPECIFIC expectation that the naive reading destroys.
        naive_default = _fixture_findings(root, _naive_default_theme())
        record(
            "NEGATIVE CONTROL A: Tailwind's default scale MISSES w-32 and p-7",
            not any(u in {"w-32", "p-7"} for _, u in naive_default),
            f"naive-defaults reported {sorted(naive_default)}",
        )
        naive_grid = _fixture_findings(root, _naive_grid_theme())
        record(
            "NEGATIVE CONTROL B: a 4px-grid guess FALSE-POSITIVES on p-1.5/h-px",
            any(path.endswith("Good.tsx") for path, _ in naive_grid),
            f"naive-grid reported {sorted(naive_grid)}",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    width = max(len(name) for name, _, _ in checks)
    failed = 0
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name.ljust(width)}")
        if not ok:
            failed += 1
            if detail:
                print(f"        {detail}")
    if failed:
        print(f"\ncheck-tailwind-scale --self-test: {failed} of {len(checks)} FAILED")
        return 1
    print(f"\ncheck-tailwind-scale --self-test: {len(checks)} checks passed")
    return 0


# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    verbose = "--verbose" in argv
    try:
        findings, files, candidates, theme = check_tree(REPO_ROOT)
    except Refusal as exc:
        print(f"check-tailwind-scale: REFUSING — {exc}", file=sys.stderr)
        return 2

    if verbose:
        for key in sorted(theme.replaced):
            steps = " ".join(sorted(theme.replaced[key], key=_scale_sort))
            print(f"  theme.{key} = {steps}")
        for key in sorted(theme.extended):
            print(f"  theme.extend.{key} += {' '.join(sorted(theme.extended[key]))}")
        covered = sorted(set(SPACING_FAMILIES) | set(REPLACED_FAMILIES))
        print(f"  covered families ({len(covered)}): {' '.join(covered)}")

    if findings:
        print(
            "check-tailwind-scale: these utilities appear in scanned source but "
            "this theme emits NO rule for them, so the element gets NO style —\n"
            "zero width, zero padding, and a DOM that looks perfect.\n",
            file=sys.stderr,
        )
        for f in sorted(findings, key=lambda f: (f.path, f.line, f.utility)):
            print(f"  {f.path}:{f.line}: {f.utility}", file=sys.stderr)
            print(f"      scale has: {f.valid}", file=sys.stderr)
        print(
            "\nFix by using a step that exists, an arbitrary value "
            "(`w-[3.5rem]`), or a named token in the preset's `extend` — NOT by "
            "reopening the scale unless the step belongs to the design language.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check-tailwind-scale: {candidates} scale-keyed utilities across "
        f"{files} scanned files, all resolvable."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""The dogfooded canopy drawings compose CLEANLY — a gate over the real artifact.

`docs/canopy/canopy_sheet.py` drafts the door-canopy construction sheets with the
same server composer the product ships, and those sheets are the only arc-bearing
drawing in the repo (geometry-QA's census: the 35 byte-level golden tests contain
8560 line, 6318 polyline and 502 circle edges and **zero arcs**, against a global
population of 255). They were therefore the artifact where ARC-BOUNDS-INFLATE-1 was
visible and nothing was watching.

This is the check that was missing, and its absence is what let a WORKAROUND OUTLIVE
ITS BUG: `s2-bracket` carries a hand anchor (`place`) added in `717fcdb` and tuned
against the INFLATED arc bounds. With those bounds corrected the anchor is simply
wrong, and nothing said so, because no test composed these sheets at all. A fixture
that exists only as a documentation script is not gated by anything — so it is gated
here, in the suite that owns the composer.

Deliberately reading `canopy_sheet.SHEETS` and calling its own `compose()` rather
than restating the request: a gate that rebuilds its subject's input is testing a
copy, and the copy is free to drift from the artifact anyone actually generates.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from py_kit.schemas.drawings import ComposedSheet

#: `services/geometry/tests/<this file>` -> repo root -> the canopy fixtures.
_CANOPY_DIR = Path(__file__).resolve().parents[3] / "docs" / "canopy"
_INK_PATH = Path(__file__).resolve().parent / "_composed_ink.py"


def _load_sibling(name: str, path: Path) -> ModuleType:
    """Load a sibling test helper (the suite's `--import-mode=importlib` idiom)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_INK = _load_sibling("_composed_ink", _INK_PATH)


def _load_canopy_sheet() -> tuple[
    dict[str, dict[str, object]], Callable[[str, dict[str, object]], object]
]:
    """Load `docs/canopy/canopy_sheet.py` BY PATH and hand back its two members.

    By path rather than by `sys.path` insertion: a test that prepends a directory to
    the interpreter's search path changes module resolution for every test that runs
    after it in the same process, which is a shadowing hazard nobody would look for
    here. The script's own `sys.path` line still resolves its `canopy_model` import,
    so loading it this way runs it exactly as `uv run python docs/canopy/...` does.
    """
    module = _load_sibling("loft_canopy_sheet_fixture", _CANOPY_DIR / "canopy_sheet.py")
    sheets: dict[str, dict[str, object]] = module.SHEETS
    compose: Callable[[str, dict[str, object]], object] = module.compose
    return sheets, compose


_SHEETS, _COMPOSE = _load_canopy_sheet()

#: The sheets this gate expects to find. A COUNT FLOOR, not decoration: parametrising
#: over a dict that silently became empty (a renamed script, a moved fixture) would
#: make every assertion below vacuously true and the gate would report success while
#: examining nothing.
_EXPECTED_SHEETS = {"s1-general-arrangement", "s2-bracket"}

#: Placement tolerance (mm). Sheet-millimetre layout arithmetic, not a geometric
#: comparison, so the residual is float noise on a handful of additions — the arc
#: defect this guards against displaces by 104.09 mm, six orders of magnitude out.
_PLACEMENT_TOL = 1e-6


def test_the_canopy_fixture_still_carries_the_sheets_this_gate_measures() -> None:
    """The floor: the fixture is present and has not quietly lost a sheet."""
    assert set(_SHEETS) == _EXPECTED_SHEETS, sorted(_SHEETS)


def _compose(name: str, spec: dict[str, object]) -> ComposedSheet:
    return cast(ComposedSheet, _COMPOSE(name, spec))


def _auto_placed(spec: dict[str, object]) -> dict[str, object]:
    """The same sheet with every view AUTO-placed (any hand anchor dropped).

    `canopy_sheet.compose` sets `auto_place` from the presence of `place`, so
    removing the key is exactly "let the composer decide" — the path a user takes
    when they have not hand-positioned anything, and the one the arc fix corrects.
    """
    return {key: value for key, value in spec.items() if key != "place"}


@pytest.mark.parametrize("name", sorted(_EXPECTED_SHEETS))
def test_every_canopy_sheet_auto_places_with_no_layout_issues(name: str) -> None:
    """Auto-layout puts the canopy's curved parts on the paper with nothing to report.

    NOT an arc gate, and saying so matters: MEASURED against the pre-fix composer,
    both canopy sheets still report `layout_issues == []`, because A2/A1 are large
    enough to absorb the arc defect's displacement without any ink crossing a
    border. This gate covers the STALE-ANCHOR / off-sheet class (see the
    as-committed case below, which the bug's own workaround now fails). The arc
    defect is observable on this artifact only as MISPLACEMENT, which is what
    `..._centres_the_bracket_on_the_paper` asserts.
    """
    sheet = _compose(name, _auto_placed(_SHEETS[name]))
    assert sheet.layout_issues == [], [
        (issue.code, issue.views, issue.message) for issue in sheet.layout_issues
    ]


def test_auto_layout_centres_the_bracket_on_the_paper() -> None:
    """THE arc gate over real geometry: the bracket's ink lands in the MIDDLE.

    The bracket sheet is a single auto-placed view of a part whose knee braces are
    two large arcs (r = 164.492 mm at 1:5) with centres far outside the drawn
    profile, so `bounds_aware_layout` centring the view's BOUNDS on the sheet is
    only correct if those bounds are the ink's. Pre-fix they were the full CIRCLES'
    — 2.07x the true width — and the drawn profile sat 104.09 mm right of centre
    (x 303.81 .. 498.37 against a 594 mm sheet) while every existing check stayed
    silent, because it was still on the paper.

    Asserted on the geometry's own centre rather than a fixed coordinate, so it
    survives any future re-layout that keeps the sheet honest. The caption band is
    excluded deliberately: the layout centres CONTENT, and the band's 9.7 mm is a
    separate, documented residual (DRAWSHEET-AUTOPLACE-1).
    """
    sheet = _compose("s2-bracket", _auto_placed(_SHEETS["s2-bracket"]))
    drawn = [v for v in sheet.views if not v.failed]
    assert len(drawn) == 1, [v.projection for v in sheet.views]
    content = _INK.composed_content_rect(drawn[0])
    assert content is not None, "the bracket view drew nothing to measure"

    assert content.center_x == pytest.approx(sheet.width_mm / 2, abs=_PLACEMENT_TOL)
    assert content.center_y == pytest.approx(sheet.height_mm / 2, abs=_PLACEMENT_TOL)
    # Non-vacuity: a view that drew almost nothing would centre trivially. The
    # bracket is a real 194 x 252 mm elevation at 1:5.
    assert content.width > 150.0, content
    assert content.height > 200.0, content


@pytest.mark.parametrize(
    "name",
    [
        "s1-general-arrangement",
        "s2-bracket",
    ],
)
def test_every_canopy_sheet_composes_as_committed_with_no_layout_issues(
    name: str,
) -> None:
    """The sheets AS THE SCRIPT WOULD DRAW THEM TODAY, hand anchors and all.

    The auto-placed gate above cannot see a stale hand anchor, because it drops the
    anchor — so this one keeps the committed spec verbatim. It is the check whose
    absence is the finding: a workaround for a bug is only safe while something
    re-measures it after the bug is fixed.
    """
    sheet = _compose(name, _SHEETS[name])
    assert sheet.layout_issues == [], [
        (issue.code, issue.views, issue.message) for issue in sheet.layout_issues
    ]

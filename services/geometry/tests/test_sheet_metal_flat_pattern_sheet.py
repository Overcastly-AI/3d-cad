"""Composed FLAT-PATTERN SHEET — slice #4 backend gate (sheet-metal §7 / §4.2).

The evaluate-path flat-pattern view (``tests/test_sheet_metal_flat_pattern_view.py``)
is now COMPOSED onto a sheet: the additive flat-pattern branch of
:func:`geometry.drawings.place_sheet` places the single flat blank CENTRED on the sheet
(reusing the SAME extent-driven ``view_to_svg_edges``/``view_bounds`` machinery every
standard view uses — never a forked edge path) plus a quiet-corner bend-table
annotation block, producing the :class:`ComposedSheet` the DE-1c frontend renders.

Gates:

* **Composed-sheet goldens** — the authored L-bracket (N=1) and U-channel (N=2) trees,
  composed through ``place_sheet``, asserted for placement (blank centred; bend-table
  block non-overlapping the blank bbox), edge-role preservation through composition
  (``body``/``bend`` counts survive), the bend-table rows carried onto the sheet, and a
  byte-identity determinism pin (in-process + a fresh interpreter restart, §9 #4).
* **Additivity** — a standard (front/top/right/iso) sheet composes with ``bend_table``
  None and every composed edge ``edge_role='body'`` (the new fields never perturb an
  ordinary sheet — the committed standard SVG/PDF/DXF byte goldens in
  ``tests/test_drawings_compose.py`` prove the serialized bytes are unchanged).
* **Honest failure** — a flat_pattern compose over a non-sheet-metal body marks the
  view failed (no crash); the typed ``flat_pattern_not_sheet_metal`` rides the evaluate
  path (:class:`DrawingViewResult`) the sheet is composed from.
"""

import hashlib
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

import pytest
from geometry.drawings import evaluate_drawing_views, place_sheet
from py_kit.schemas.drawings import (
    ComposedLineEdge,
    ComposeDrawingRequest,
    ComposedSheet,
    SheetLayout,
    SheetPoint,
    SheetSize,
    SheetViewPlacement,
    ViewScale,
)
from py_kit.schemas.features import EvaluateTreeRequest
from pydantic import BaseModel, ConfigDict, Field

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"

_SCALE = ViewScale(numerator=1, denominator=1)


class _ExpectedBendRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bend_id: str
    angle_deg: float
    radius_mm: float
    direction: str
    bend_allowance_mm: float


class _ExpectedFlatPatternSheet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    title: str
    sheet_size: SheetSize
    orientation: str
    body_edge_count: int
    bend_edge_count: int
    bend_table: list[_ExpectedBendRow]
    content_hash: str


_GOLDEN_DIRS = sorted(
    d.parent for d in _GOLDENS_DIR.glob("*-flat-pattern-sheet/expected.json")
)
each_golden = pytest.mark.parametrize(
    "golden_dir", _GOLDEN_DIRS, ids=[d.name for d in _GOLDEN_DIRS]
)


def test_flat_pattern_sheet_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert _GOLDEN_DIRS, f"no *-flat-pattern-sheet goldens under {_GOLDENS_DIR}"


def _features_request(golden_dir: Path) -> EvaluateTreeRequest:
    """The shared feature tree from the sibling flat-pattern-VIEW golden (DRY)."""
    name = golden_dir.name.replace("-flat-pattern-sheet", "")
    return EvaluateTreeRequest.model_validate_json(
        (_GOLDENS_DIR / f"{name}-flat-pattern-view/model.json").read_text("utf-8")
    )


def _compose_request(
    golden_dir: Path, expected: _ExpectedFlatPatternSheet
) -> ComposeDrawingRequest:
    tree = _features_request(golden_dir)
    return ComposeDrawingRequest(
        part_id=tree.part_id,
        tree_version=tree.tree_version,
        features=tree.features,
        views=["flat_pattern"],
        scale=_SCALE,
        dimensions=[],
        layout=SheetLayout(
            size=expected.sheet_size,
            orientation="landscape",
            title=expected.title,
            views=[
                SheetViewPlacement(
                    projection="flat_pattern",
                    position=SheetPoint(x_mm=0.0, y_mm=0.0),
                    scale=_SCALE,
                )
            ],
        ),
        format="svg",
    )


def _load(golden_dir: Path) -> _ExpectedFlatPatternSheet:
    return _ExpectedFlatPatternSheet.model_validate_json(
        (golden_dir / "expected.json").read_text("utf-8")
    )


def _compose(golden_dir: Path, expected: _ExpectedFlatPatternSheet) -> ComposedSheet:
    request = _compose_request(golden_dir, expected)
    evaluation = evaluate_drawing_views(request)
    return place_sheet(evaluation, request.dimensions, request.layout)


def _blank_bbox(sheet: ComposedSheet) -> tuple[float, float, float, float]:
    """min_x, min_y, max_x, max_y of the flat blank's placed line edges (SVG mm)."""
    xs: list[float] = []
    ys: list[float] = []
    view = sheet.views[0]
    for edge in view.edges:
        assert isinstance(edge, ComposedLineEdge)  # a flat pattern is all lines
        xs += [edge.x1, edge.x2]
        ys += [edge.y1, edge.y2]
    return min(xs), min(ys), max(xs), max(ys)


@each_golden
def test_flat_pattern_sheet_placement_and_bend_table(golden_dir: Path) -> None:
    """The blank is centred; the bend table is present, populated, and clear of it."""
    expected = _load(golden_dir)
    sheet = _compose(golden_dir, expected)
    tol = expected.tolerance

    # A single placed flat-pattern view, not failed.
    assert [v.projection for v in sheet.views] == ["flat_pattern"]
    view = sheet.views[0]
    assert not view.failed
    assert view.label == "FLAT PATTERN"

    # Edge-role preservation THROUGH composition: the compose transform keeps the
    # body/bend split the evaluate path emitted (never dropped in view_to_svg_edges).
    roles = Counter(e.edge_role for e in view.edges)
    assert roles["body"] == expected.body_edge_count
    assert roles["bend"] == expected.bend_edge_count

    # The blank is placed CENTRED — its projected-extent bbox centre coincides with
    # the sheet centre (extent-driven placement, reusing view_bounds).
    min_x, min_y, max_x, max_y = _blank_bbox(sheet)
    assert (min_x + max_x) / 2 == pytest.approx(sheet.width_mm / 2, abs=tol)
    assert (min_y + max_y) / 2 == pytest.approx(sheet.height_mm / 2, abs=tol)

    # The bend table surfaces on the ComposedSheet (rows + anchor rect), correlated
    # POSITIONALLY to the bend edges (row count == bend-edge count).
    bt = sheet.bend_table
    assert bt is not None
    assert len(bt.rows) == expected.bend_edge_count
    assert len(bt.rows) == len(expected.bend_table)
    for row, exp in zip(bt.rows, expected.bend_table, strict=True):
        assert row.bend_id == exp.bend_id
        assert row.direction == exp.direction
        assert row.angle_deg == pytest.approx(exp.angle_deg, abs=tol)
        assert row.radius_mm == pytest.approx(exp.radius_mm, abs=tol)
        assert row.bend_allowance_mm == pytest.approx(exp.bend_allowance_mm, abs=tol)

    # The bend-table block does NOT overlap the blank's bbox (a quiet corner).
    tx0, ty0, tx1, ty1 = bt.x, bt.y, bt.x + bt.width, bt.y + bt.height
    overlap_w = min(tx1, max_x) - max(tx0, min_x)
    overlap_h = min(ty1, max_y) - max(ty0, min_y)
    assert not (overlap_w > 0 and overlap_h > 0), "bend table overlaps the blank"

    # The block sits inside the sheet border.
    assert tx0 >= sheet.margin_mm - tol and ty0 >= sheet.margin_mm - tol
    assert tx1 <= sheet.width_mm - sheet.margin_mm + tol


@each_golden
def test_flat_pattern_sheet_is_deterministic_in_process(golden_dir: Path) -> None:
    """Same request twice → byte-identical ComposedSheet JSON == the pin (§9 #4)."""
    expected = _load(golden_dir)
    a = _compose(golden_dir, expected)
    b = _compose(golden_dir, expected)
    assert a.model_dump_json() == b.model_dump_json()
    assert hashlib.sha256(a.model_dump_json().encode()).hexdigest() == (
        expected.content_hash
    )


_RESTART_PROBE = """\
import hashlib
import sys
from pathlib import Path

from geometry.drawings import evaluate_drawing_views, place_sheet
from py_kit.schemas.drawings import (
    ComposeDrawingRequest, SheetLayout, SheetPoint, SheetViewPlacement, ViewScale,
)
from py_kit.schemas.features import EvaluateTreeRequest

view_model, size, orientation, title = sys.argv[1:5]
scale = ViewScale(numerator=1, denominator=1)
tree = EvaluateTreeRequest.model_validate_json(Path(view_model).read_text("utf-8"))
request = ComposeDrawingRequest(
    part_id=tree.part_id, tree_version=tree.tree_version, features=tree.features,
    views=["flat_pattern"], scale=scale, dimensions=[],
    layout=SheetLayout(size=size, orientation=orientation, title=title,
        views=[SheetViewPlacement(projection="flat_pattern",
            position=SheetPoint(x_mm=0.0, y_mm=0.0), scale=scale)]),
    format="svg")
sheet = place_sheet(evaluate_drawing_views(request), request.dimensions, request.layout)
print(hashlib.sha256(sheet.model_dump_json().encode()).hexdigest())
"""


@each_golden
def test_flat_pattern_sheet_is_deterministic_across_restart(golden_dir: Path) -> None:
    """A fresh interpreter reproduces the byte-identical composed-sheet hash (§9 #4)."""
    expected = _load(golden_dir)
    name = golden_dir.name.replace("-flat-pattern-sheet", "")
    view_model = _GOLDENS_DIR / f"{name}-flat-pattern-view/model.json"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _RESTART_PROBE,
            str(view_model),
            expected.sheet_size,
            expected.orientation,
            expected.title,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout.splitlines()[0] == expected.content_hash


# --------------------------------------------------------------------------- #
# Additivity + honest failure                                                 #
# --------------------------------------------------------------------------- #


def _box_part() -> EvaluateTreeRequest:
    """A plain (non-sheet-metal) box part: sketch + extrude."""
    sk = "00000000-0000-0000-0000-0000000080a0"
    ex = "00000000-0000-0000-0000-0000000080b0"
    return EvaluateTreeRequest.model_validate(
        {
            "part_id": str(uuid.uuid4()),
            "tree_version": 1,
            "features": [
                {
                    "id": sk,
                    "feature": {
                        "type": "sketch",
                        "version": 1,
                        "params": {
                            "plane": {"kind": "datum_plane", "plane": "XY"},
                            "entities": [
                                {
                                    "id": "e1",
                                    "kind": "line",
                                    "start": {"x": 0.0, "y": 0.0},
                                    "end": {"x": 40.0, "y": 0.0},
                                },
                                {
                                    "id": "e2",
                                    "kind": "line",
                                    "start": {"x": 40.0, "y": 0.0},
                                    "end": {"x": 40.0, "y": 25.0},
                                },
                                {
                                    "id": "e3",
                                    "kind": "line",
                                    "start": {"x": 40.0, "y": 25.0},
                                    "end": {"x": 0.0, "y": 25.0},
                                },
                                {
                                    "id": "e4",
                                    "kind": "line",
                                    "start": {"x": 0.0, "y": 25.0},
                                    "end": {"x": 0.0, "y": 0.0},
                                },
                            ],
                            "constraints": [],
                        },
                    },
                },
                {
                    "id": ex,
                    "feature": {
                        "type": "extrude",
                        "version": 1,
                        "params": {
                            "profile": {"kind": "feature", "feature_id": sk},
                            "distance_mm": 10.0,
                            "operation": "add",
                        },
                    },
                },
            ],
        }
    )


def _standard_request(views: list[str]) -> ComposeDrawingRequest:
    box = _box_part()
    return ComposeDrawingRequest(
        part_id=box.part_id,
        tree_version=box.tree_version,
        features=box.features,
        views=views,  # type: ignore[arg-type]
        scale=_SCALE,
        dimensions=[],
        layout=SheetLayout(
            size="A4",
            orientation="landscape",
            title="Box",
            views=[
                SheetViewPlacement(
                    projection=v,  # type: ignore[arg-type]
                    position=SheetPoint(x_mm=0.0, y_mm=0.0),
                    scale=_SCALE,
                )
                for v in views
            ],
        ),
        format="svg",
    )


def test_standard_sheet_is_unperturbed_by_the_flat_pattern_branch() -> None:
    """A standard (HLR) sheet composes with bend_table None and every composed edge
    edge_role='body' — the flat-pattern branch is purely additive."""
    request = _standard_request(["front", "top", "right", "iso"])
    evaluation = evaluate_drawing_views(request)
    sheet = place_sheet(evaluation, request.dimensions, request.layout)

    assert sheet.bend_table is None
    assert [v.projection for v in sheet.views] == ["front", "top", "right", "iso"]
    for view in sheet.views:
        for edge in view.edges:
            assert edge.edge_role == "body"


def test_flat_pattern_compose_over_non_sheet_metal_body_is_failed_not_crash() -> None:
    """A flat_pattern compose of a plain body marks the view failed (no crash); the
    typed flat_pattern_not_sheet_metal rides the evaluate DrawingViewResult."""
    request = _standard_request(["flat_pattern"])
    evaluation = evaluate_drawing_views(request)
    # The evaluate path surfaces the typed per-view error.
    assert evaluation.views[0].error is not None
    assert evaluation.views[0].error.code == "flat_pattern_not_sheet_metal"

    sheet = place_sheet(evaluation, request.dimensions, request.layout)
    assert [v.projection for v in sheet.views] == ["flat_pattern"]
    assert sheet.views[0].failed
    assert sheet.views[0].edges == []
    assert sheet.bend_table is None  # no table for a failed unfold

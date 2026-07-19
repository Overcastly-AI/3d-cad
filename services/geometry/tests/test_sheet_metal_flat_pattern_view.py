"""Flat-pattern DRAWING VIEW — slice #4 backend gate (sheet-metal §7 / drawings §7).

A sheet-metal body's unfold requested AS a drawing view (projection = 'flat_pattern'):
geometry evaluates the part once, SKIPS HLR, unfolds the depth-1 bend star, and feeds
the FlatPattern's ``edge_role``-tagged outline straight into the SHIPPED neutral
``ProjectedViewEdge`` / ``DrawingViewResult`` shape, plus a per-bend bend table.

Three halves:

* **Flat-pattern-view goldens** — the authored L-bracket (N=1) and U-channel (N=2)
  feature trees, resolved through :func:`geometry.drawings.flat_pattern_view_result`,
  asserted against edge counts by role, the analytic bend table, and a byte-identity
  determinism pin (in-process + a fresh interpreter restart, §9 #4).
* **Additivity** — a standard HLR view carries ``edge_role='body'`` on every edge and
  an empty bend table, so the new fields never perturb an existing drawing consumer.
* **Honest per-view failure** — a non-sheet-metal part asked for a flat_pattern view
  is a typed ``flat_pattern_not_sheet_metal`` (never a crash); a mixed request keeps
  the other views intact; an unresolvable bend degrades to ``subshape_unresolved``.

Does NOT touch ``tests/test_sheet_metal.py`` (Spike 0) or the shared ``goldens/``.
"""

import hashlib
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

import pytest
from geometry.drawings import evaluate_drawing_views, flat_pattern_view_result
from geometry.features.evaluate import evaluate_tree
from py_kit.schemas.drawings import (
    DrawingViewResult,
    EvaluateDrawingViewsRequest,
    ViewScale,
)
from py_kit.schemas.features import EvaluateTreeRequest
from pydantic import BaseModel, ConfigDict, Field

_HERE = Path(__file__).resolve().parent
_GOLDENS_DIR = _HERE.parent / "goldens-sheet-metal"

_UNIT_SCALE = ViewScale(numerator=1, denominator=1)


class _ExpectedBendRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bend_id: str
    angle_deg: float
    radius_mm: float
    direction: str
    bend_allowance_mm: float


class _ExpectedFlatPatternView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    derivation: list[str]
    tolerance: float = Field(gt=0)
    tolerance_rationale: str
    scale: ViewScale
    body_edge_count: int
    bend_edge_count: int
    bend_table: list[_ExpectedBendRow]
    content_hash: str


_GOLDEN_DIRS = sorted(
    model.parent for model in _GOLDENS_DIR.glob("*-flat-pattern-view/model.json")
)
each_golden = pytest.mark.parametrize(
    "golden_dir", _GOLDEN_DIRS, ids=[d.name for d in _GOLDEN_DIRS]
)


def test_flat_pattern_view_golden_inventory_is_nonempty() -> None:
    """Discovery breakage must fail the suite, never silently pass it."""
    assert _GOLDEN_DIRS, f"no *-flat-pattern-view goldens under {_GOLDENS_DIR}"


def _load(golden_dir: Path) -> tuple[EvaluateTreeRequest, _ExpectedFlatPatternView]:
    request = EvaluateTreeRequest.model_validate_json(
        (golden_dir / "model.json").read_text("utf-8")
    )
    expected = _ExpectedFlatPatternView.model_validate_json(
        (golden_dir / "expected.json").read_text("utf-8")
    )
    return request, expected


def _view(request: EvaluateTreeRequest, scale: ViewScale) -> DrawingViewResult:
    evaluation = evaluate_tree(request)
    assert all(f.status == "ok" for f in evaluation.result.features)
    return flat_pattern_view_result(evaluation, scale)


@each_golden
def test_flat_pattern_view_edges_and_bend_table(golden_dir: Path) -> None:
    """The flat pattern projects to the analytic edge_role outline + bend table."""
    request, expected = _load(golden_dir)
    result = _view(request, expected.scale)
    tol = expected.tolerance

    assert result.error is None, result.error
    assert result.view == "flat_pattern"

    roles = Counter(e.edge_role for e in result.edges)
    assert roles["body"] == expected.body_edge_count
    assert roles["bend"] == expected.bend_edge_count
    # Every outline edge is a straight, visible line (a flat pattern occludes nothing).
    assert all(e.primitive == "line" and e.visible for e in result.edges)

    assert len(result.bend_table) == len(expected.bend_table)
    for row, exp in zip(result.bend_table, expected.bend_table, strict=True):
        assert row.bend_id == exp.bend_id
        assert row.direction == exp.direction
        assert row.angle_deg == pytest.approx(exp.angle_deg, abs=tol)
        assert row.radius_mm == pytest.approx(exp.radius_mm, abs=tol)
        assert row.bend_allowance_mm == pytest.approx(exp.bend_allowance_mm, abs=tol)

    # Each bend row's id has a matching edge_role='bend' outline edge (§6).
    bend_edge_ids_ok = roles["bend"] == len(result.bend_table)
    assert bend_edge_ids_ok


@each_golden
def test_flat_pattern_view_is_deterministic_in_process(golden_dir: Path) -> None:
    """Same tree twice → byte-identical DrawingViewResult JSON (§9 #4)."""
    request, expected = _load(golden_dir)
    a = _view(request, expected.scale)
    b = _view(request, expected.scale)
    assert a.model_dump_json() == b.model_dump_json()
    assert hashlib.sha256(a.model_dump_json().encode()).hexdigest() == (
        expected.content_hash
    )


_RESTART_PROBE = """\
import hashlib
import sys
from pathlib import Path

from geometry.drawings import flat_pattern_view_result
from geometry.features.evaluate import evaluate_tree
from py_kit.schemas.drawings import ViewScale
from py_kit.schemas.features import EvaluateTreeRequest

request = EvaluateTreeRequest.model_validate_json(Path(sys.argv[1]).read_text("utf-8"))
result = flat_pattern_view_result(
    evaluate_tree(request), ViewScale(numerator=1, denominator=1)
)
print(hashlib.sha256(result.model_dump_json().encode()).hexdigest())
"""


@each_golden
def test_flat_pattern_view_is_deterministic_across_restart(golden_dir: Path) -> None:
    """Fresh-interpreter rebuild reproduces the byte-identical view hash (§9 #4)."""
    _, expected = _load(golden_dir)
    result = subprocess.run(
        [sys.executable, "-c", _RESTART_PROBE, str(golden_dir / "model.json")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout.splitlines()[0] == expected.content_hash


# --------------------------------------------------------------------------- #
# Additivity + honest per-view failure                                        #
# --------------------------------------------------------------------------- #


def _box_part() -> EvaluateTreeRequest:
    """A plain (non-sheet-metal) box part: sketch + extrude."""
    sk = "00000000-0000-0000-0000-0000000070a0"
    ex = "00000000-0000-0000-0000-0000000070b0"
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
                                {"id": "e1", "kind": "line",
                                 "start": {"x": 0.0, "y": 0.0},
                                 "end": {"x": 40.0, "y": 0.0}},
                                {"id": "e2", "kind": "line",
                                 "start": {"x": 40.0, "y": 0.0},
                                 "end": {"x": 40.0, "y": 25.0}},
                                {"id": "e3", "kind": "line",
                                 "start": {"x": 40.0, "y": 25.0},
                                 "end": {"x": 0.0, "y": 25.0}},
                                {"id": "e4", "kind": "line",
                                 "start": {"x": 0.0, "y": 25.0},
                                 "end": {"x": 0.0, "y": 0.0}},
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


def test_flat_pattern_of_non_sheet_metal_is_typed_error() -> None:
    """A flat_pattern view of a plain body is a typed per-view error, not a crash."""
    evaluation = evaluate_tree(_box_part())
    result = flat_pattern_view_result(evaluation, _UNIT_SCALE)
    assert result.edges == []
    assert result.bend_table == []
    assert result.error is not None
    assert result.error.code == "flat_pattern_not_sheet_metal"


def test_mixed_request_keeps_standard_view_intact_and_additive() -> None:
    """A request mixing flat_pattern + a standard view: the flat pattern resolves via
    the SAME envelope, and the standard HLR view is unaffected — every edge defaults to
    edge_role='body' with an empty bend table (additivity of the new fields)."""
    tree = EvaluateTreeRequest.model_validate_json(
        (_GOLDENS_DIR / "l-bracket-flat-pattern-view/model.json").read_text("utf-8")
    )
    request = EvaluateDrawingViewsRequest(
        part_id=tree.part_id,
        tree_version=tree.tree_version,
        features=tree.features,
        views=["flat_pattern", "front"],
    )
    result = evaluate_drawing_views(request)
    assert [v.view for v in result.views] == ["flat_pattern", "front"]

    flat, front = result.views
    assert flat.error is None and len(flat.bend_table) == 1
    assert any(e.edge_role == "bend" for e in flat.edges)

    assert front.error is None
    assert front.bend_table == []
    assert front.edges  # HLR produced geometry
    assert all(e.edge_role == "body" for e in front.edges)


def test_flat_pattern_view_unresolvable_bend_degrades_honestly() -> None:
    """A flat_pattern view whose bend signature no longer resolves is a typed
    subshape_unresolved on THAT view (never a wrong flat pattern, §5)."""
    from build123d import Box
    from geometry.features.evaluate import TreeEvaluation
    from geometry.kernel.edges import enumerate_edges
    from geometry.sheet_metal import BendProvenance, build_edge_flange

    base = Box(40.0, 20.0, 2.0).translate((20.0, 10.0, 1.0))
    edge = next(
        rec.edge
        for rec in enumerate_edges(base)
        if abs((rec.edge @ 0.0).X - 40.0) < 1e-9
        and abs((rec.edge @ 1.0).X - 40.0) < 1e-9
        and abs((rec.edge @ 0.5).Z - 2.0) < 1e-9
        and rec.signature.curve == "line"
    )
    built = build_edge_flange(base, edge, 30.0, 90.0, 3.0, 2.0)
    from geometry.sheet_metal import SheetMetalDefaults

    # A TreeEvaluation whose body is the ORIGINAL flat base (the bend face is gone),
    # but whose provenance still references the bend → an honest subshape_unresolved.
    evaluation = TreeEvaluation(
        result=evaluate_tree(_box_part()).result,  # a real ok result envelope
        solved_sketches={},
        body=base,
        bend_provenance=[
            BendProvenance(built.cyl_signature, built.base_face_signature, 0.44)
        ],
        sheet_metal_defaults=SheetMetalDefaults(
            thickness_mm=2.0, k_factor=0.44, bend_radius_mm=3.0
        ),
    )
    result = flat_pattern_view_result(evaluation, _UNIT_SCALE)
    assert result.error is not None
    assert result.error.code == "subshape_unresolved"

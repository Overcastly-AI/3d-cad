"""Cross tubes that end on, past, or at the skin of a same-diameter rail tube.

BACKLOG BOOLEAN-COINCIDENT-TUBE. The moto-frame golden's four Y cross tubes
end 6 mm inside the rail centrelines. An engineer models them centreline to
centreline (220 long), so this drives the SAME tree with the tubes ending where
they would: the shipped answer must be right, refused, or flagged, never a
silently wrong solid.

Measured 2026-10-07 through ``evaluate_tree`` (the product's path):

* on the centreline (y = +-110): builds, 708479.158 mm^3, one valid lump. Right:
  the twin built with tubes 109.99 .. 108 mm (smooth, dV/dy -> 783.14 mm^3/mm)
  extrapolates to 708479.161, 3e-3 away. STEP re-read differs by 1.1e-2.
* 0.5 mm past (y = +-110.5): refused, the last union fails ``invalid_body`` and
  the rest are skipped; the shipped body is the strict prefix. Right.
* at the rail's outer skin (y = +-122.7): builds with every feature ``ok``,
  one lump that passes BRepCheck, STEP re-reads to the same number, and reads
  732801.92 mm^3 with 18 shells. WRONG: a union cannot exceed the sum of its
  members, 2 rails + 4 tubes of 245.4 + the head = 725460.9 mm^3 (closed forms
  below), and the build123d twin fused with tubes ending 0.1 mm past the skin
  gives 729715.6, which minus the 0.1 mm of tube past the skin (8 * area *
  0.1 = 95.7) puts the truth near 729620.
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from geometry.features import evaluate_tree
from geometry.kernel import measure_shape
from loft_wire.features import EvaluateTreeRequest

GOLDEN = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "frame-moto-cradle-tube-od25.4-t1.6"
    / "model.json"
)

ANNULUS_AREA = math.pi * (12.7**2 - 11.1**2)
RAIL_VOLUME = ANNULUS_AREA * 1766.0415908222212  # Pappus, closed loop length
HEAD_VOLUME = math.pi * (25.0**2 - 16.0**2) * 160.0


def _frame_with_tubes_ending_at(y: float) -> EvaluateTreeRequest:
    """The golden's tree, the four cross tubes extruded from y to -y."""
    data: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for item in data["features"]:
        params = item["feature"]["params"]
        if item["feature"]["type"] == "datum" and item["id"].endswith("04"):
            params["offset_mm"] = -y  # the XZ datum's normal is -Y
        if item["feature"]["type"] == "extrude":
            params["distance_mm"] = 2 * y
    return EvaluateTreeRequest.model_validate(data)


def test_tubes_ending_on_the_rail_centreline_are_right() -> None:
    evaluation = evaluate_tree(_frame_with_tubes_ending_at(110.0))
    assert all(r.status == "ok" for r in evaluation.result.features)
    assert evaluation.body is not None
    # Twin extrapolated from tubes ending at 109.99 and below (see module doc).
    assert measure_shape(evaluation.body).volume == pytest.approx(708479.161, abs=0.05)
    assert len(evaluation.body.solids()) == 1


def test_tubes_ending_past_the_centreline_are_refused_not_shipped_wrong() -> None:
    evaluation = evaluate_tree(_frame_with_tubes_ending_at(110.5))
    errors = [r for r in evaluation.result.features if r.error is not None]
    assert errors, "a body the kernel rejects must not build clean"
    assert {r.error.code for r in errors if r.error} == {"invalid_body"}


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="BACKLOG BOOLEAN-COINCIDENT-TUBE: tubes ending at the rail's outer "
    "skin (y=+-122.7) build with every feature ok and a BRepCheck-valid lump, "
    "but read 732801.9 mm^3 against an upper bound of 725460.9 (and a truth "
    "near 729620), with 18 shells",
)
def test_tubes_ending_at_the_rail_skin_do_not_exceed_the_sum_of_their_members() -> None:
    evaluation = evaluate_tree(_frame_with_tubes_ending_at(122.7))
    if any(r.error is not None for r in evaluation.result.features):
        return  # a refusal would be right too; the xfail then XPASSes and flags it
    assert evaluation.body is not None
    members = 2 * RAIL_VOLUME + 4 * ANNULUS_AREA * 2 * 122.7 + HEAD_VOLUME
    assert measure_shape(evaluation.body).volume <= members

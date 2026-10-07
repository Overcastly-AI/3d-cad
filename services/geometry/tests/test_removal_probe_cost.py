"""The removal probe costs one classification, not a second whole-body boolean.

PERF (RESEARCH §15). On the 200-feature tray every subtractive feature asked
"does this tool reach the body?" with a full boolean COMMON before the cut, and
a Hole then ran the SAME common again to measure its pocket: three whole-body
booleans per hole, two per cut, 20 % of the rebuild. Now:

* an extrude cut / pattern / mirror tool whose centre of mass is strictly inside
  both itself and the body is proven to reach it by OCCT's solid classifier, and
  the common runs only when that proves nothing;
* a Hole computes its common ONCE and uses it for both the reach answer and the
  pocket measurement.

The gates below pin those as COUNTS of OCCT boolean operations (never a
wall-clock, which a loaded runner makes flaky), plus the certificate's
soundness: it may only ever say "reaches" where the boolean says so too.
"""
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

import importlib.util
import random
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from build123d import Box, Compound, Plane, Pos, Solid
from build123d.topology.shape_core import Shape
from geometry.features import evaluate_tree
from geometry.features.evaluate import reset_rebuild_cache
from geometry.kernel.extrude import CutRemovedNothingError, combine_body
from geometry.kernel.faces import planar_faces
from geometry.kernel.hole import bore_hole, cut_counterbore
from geometry.kernel.removal import removal_reaches_body, shares_interior_point
from loft_wire.features import EvaluateTreeRequest

_BUILDERS_PATH = Path(__file__).resolve().parent / "_big_part_builders.py"


def _builders() -> Any:
    spec = importlib.util.spec_from_file_location("_big_part_builders", _BUILDERS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def booleans(monkeypatch: pytest.MonkeyPatch) -> Iterator[Counter[str]]:
    """Every build123d boolean, counted by its OCCT operation class name."""
    seen: Counter[str] = Counter()
    # The one funnel every build123d boolean goes through; counted, not changed.
    original = cast(Callable[..., Any], Shape._bool_op)  # pyright: ignore[reportPrivateUsage]

    def counting(self: Any, args: Any, tools: Any, operation: Any) -> Any:
        seen[type(operation).__name__] += 1
        return original(self, args, tools, operation)

    monkeypatch.setattr(Shape, "_bool_op", counting)
    yield seen


def _plate() -> Solid:
    """60 x 40 x 10 plate, top face at z = 10."""
    return Solid(Box(60, 40, 10).moved(Pos(0, 0, 5)).wrapped)


def _top_plane(body: Solid) -> Plane:
    top = max(planar_faces(body), key=lambda record: record.plane.origin.Z)
    return top.plane


# --- the counts ---------------------------------------------------------------


def test_a_hole_runs_one_common_and_one_cut(booleans: Counter[str]) -> None:
    body = _plate()
    plane = _top_plane(body)
    booleans.clear()
    bore_hole(body, plane, (0.0, 0.0, 10.0), 5.0, through_all=False, depth_mm=4.0)
    assert booleans == Counter({"BRepAlgoAPI_Common": 1, "BRepAlgoAPI_Cut": 1})


def test_a_counterbored_hole_runs_one_common_per_cut(booleans: Counter[str]) -> None:
    body = _plate()
    plane = _top_plane(body)
    drilled = bore_hole(
        body, plane, (0.0, 0.0, 10.0), 5.0, through_all=True, depth_mm=None
    )
    booleans.clear()
    cut_counterbore(
        drilled,
        plane,
        (0.0, 0.0, 10.0),
        bore_diameter_mm=5.0,
        cbore_diameter_mm=9.0,
        cbore_depth_mm=3.0,
    )
    assert booleans == Counter({"BRepAlgoAPI_Common": 1, "BRepAlgoAPI_Cut": 1})


def test_an_embedded_pocket_cut_runs_no_common(booleans: Counter[str]) -> None:
    pocket = Solid(Box(10, 8, 3).moved(Pos(0, 0, 8.5)).wrapped)
    combine_body(_plate(), pocket, "cut")
    assert booleans == Counter({"BRepAlgoAPI_Cut": 1})


def test_a_cut_beside_the_body_is_still_refused_by_the_boolean(
    booleans: Counter[str],
) -> None:
    beside = Solid(Box(10, 8, 3).moved(Pos(100, 0, 8.5)).wrapped)
    with pytest.raises(CutRemovedNothingError):
        combine_body(_plate(), beside, "cut")
    assert booleans == Counter({"BRepAlgoAPI_Common": 1})


def test_the_tray_rebuild_runs_one_common_per_hole_and_none_per_cut(
    booleans: Counter[str],
) -> None:
    """The scaling gate. 29 features of the benchmark tray: 4 holes, 5 extrude
    cuts, a pattern and a mirror. Before RESEARCH §15 this was 4 x 2 + 7 = 15
    commons (pattern and mirror probe too); one per hole is the floor, since the
    hole must measure its pocket."""
    request = EvaluateTreeRequest.model_validate(_builders().housing_tree(29))
    holes = sum(1 for item in request.features if item.feature.type == "hole")
    reset_rebuild_cache()
    booleans.clear()
    evaluation = evaluate_tree(request)
    assert all(result.status == "ok" for result in evaluation.result.features)
    assert holes == 4
    assert booleans["BRepAlgoAPI_Common"] == holes


# --- the certificate is sound ---------------------------------------------------


def _common_has_solid(body: Solid, tool: Solid) -> bool:
    common = body.intersect(tool)
    return common is not None and bool(common.solids())


def test_a_tool_resting_on_the_body_proves_nothing() -> None:
    """Face contact, the mirror/pattern clearing-plane case: no shared volume."""
    body = _plate()
    resting = Solid(Box(10, 8, 3).moved(Pos(0, 0, 11.5)).wrapped)
    assert not shares_interior_point(body, resting)
    assert not removal_reaches_body(body, [resting])


def test_a_ring_tool_falls_back_to_the_boolean(booleans: Counter[str]) -> None:
    """A tube's centre of mass is in its bore, outside the tool, so it proves
    nothing; the boolean still answers "reaches"."""
    body = _plate()
    ring = Solid.make_cylinder(8.0, 20.0, Plane.XY.offset(-5.0)).cut(
        Solid.make_cylinder(6.0, 20.0, Plane.XY.offset(-5.0))
    )
    assert isinstance(ring, Solid)
    assert not shares_interior_point(body, ring)
    booleans.clear()
    assert removal_reaches_body(body, [ring])
    assert booleans == Counter({"BRepAlgoAPI_Common": 1})


def test_a_multi_lump_body_goes_straight_to_the_boolean() -> None:
    left = Solid(Box(10, 10, 10).moved(Pos(-20, 0, 5)).wrapped)
    right = Solid(Box(10, 10, 10).moved(Pos(20, 0, 5)).wrapped)
    body = Compound(children=[left, right])
    tool = Solid(Box(4, 4, 4).moved(Pos(20, 0, 5)).wrapped)
    assert not shares_interior_point(body, tool)
    assert removal_reaches_body(body, [tool])


def test_the_certificate_never_disagrees_with_the_boolean() -> None:
    """120 seeded boxes and cylinders scattered in and around a pocketed,
    shelled tray (29 features: pockets, holes, a boss, a slot, a turret): the
    certificate may say "reaches" ONLY where the boolean common holds a solid.
    Both answers occur, so the sweep cannot pass vacuously."""
    evaluation = evaluate_tree(
        EvaluateTreeRequest.model_validate(_builders().housing_tree(29))
    )
    body = evaluation.body
    assert isinstance(body, Solid)
    box = body.bounding_box()
    rng = random.Random(15)
    proven = boolean_yes = 0
    for index in range(120):
        x = rng.uniform(box.min.X - 10, box.max.X + 10)
        y = rng.uniform(box.min.Y - 10, box.max.Y + 10)
        z = rng.uniform(box.min.Z - 5, box.max.Z + 5)
        size = rng.uniform(1.0, 12.0)
        if index % 2:
            tool = Solid(Box(size, size * 0.7, size * 0.4).moved(Pos(x, y, z)).wrapped)
        else:
            tool = Solid.make_cylinder(
                size / 2, size, Plane.XY.offset(z).move(Pos(x, y))
            )
        certified = shares_interior_point(body, tool)
        reaches = _common_has_solid(body, tool)
        assert not certified or reaches, f"tool {index} certified but misses"
        proven += certified
        boolean_yes += reaches
    assert proven >= 20, proven
    assert boolean_yes > proven, (boolean_yes, proven)

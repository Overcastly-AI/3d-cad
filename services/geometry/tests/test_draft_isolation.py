"""Draft isolation (DRAFT-SEGFAULT).

OCCT 7.9.3 SEGFAULTS in ``BRepOffsetAPI_DraftAngle::Build`` on a 30 deg draft
of a hub's cylinder or cone face beside a lofted blade, with the hub's seam at
180 deg (at 0 deg it raises cleanly). In-process that kills the geometry
worker. A draft outside the analytic cases therefore runs in the blend server
(:mod:`geometry.kernel.fillet_isolation`), like a fillet: the crash costs the
draft, and the result of a draft that builds is the in-process result.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false
# pyright: reportAttributeAccessIssue=false

import importlib.util
import os
import subprocess
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from build123d import Axis, Box, Cylinder, Face, GeomType, Plane, Pos, Solid
from geometry.kernel import draft as draft_module
from geometry.kernel import fillet_isolation
from geometry.kernel.draft import (
    DraftError,
    DraftTimeoutError,
    draft_body,
    draft_needs_isolation,
)
from geometry.kernel.naming import OpHistory


def _load_hub() -> ModuleType:
    """``tests/_blade_hub.py``, loaded by file path (importlib import-mode)."""
    spec = importlib.util.spec_from_file_location(
        "_blade_hub", Path(__file__).with_name("_blade_hub.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HUB = _load_hub()
_cylinder_hub: Callable[[float], Solid] = _HUB.cylinder_hub
_cone_hub: Callable[[float], Solid] = _HUB.cone_hub
_round_face: Callable[[Solid], Face] = _HUB.round_face

_CRASH = """
import sys
from build123d import Plane
from geometry.kernel.draft import draft_lumps
sys.path.insert(0, sys.argv[1])
from _blade_hub import cylinder_hub, round_face
body = cylinder_hub(180.0)
plane = Plane.XY
draft_lumps(body, [round_face(body)], plane.z_dir.to_dir(), plane.wrapped, 30.0, None)
"""


def test_the_crash_is_still_in_occt() -> None:
    """The case this guards against still kills a process that runs it raw.
    When OCCT fixes it, this fails, and the isolation can be reconsidered."""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_CRASH), os.path.dirname(__file__)],
        capture_output=True,
        timeout=300,
    )
    assert result.returncode < 0, result.stderr.decode()[-2000:]


@pytest.mark.parametrize("hub", [_cylinder_hub, _cone_hub], ids=["cylinder", "cone"])
@pytest.mark.parametrize("plane", [Plane.XY, Plane.XY.offset(10)], ids=["z0", "z10"])
def test_the_crashing_draft_is_a_typed_error_and_the_process_lives(
    hub: object, plane: Plane
) -> None:
    body = hub(180.0)  # pyright: ignore[reportCallIssue, reportOperatorIssue]
    face = _round_face(body)
    assert draft_needs_isolation(body, [face])
    before = fillet_isolation.server_pid()
    with pytest.raises(DraftError, match="crashed"):
        draft_body(body, [face], plane, 30.0, history=OpHistory())
    # This process carried on, and so did the server (only its child died).
    assert fillet_isolation.server_pid() is not None
    if before is not None:
        assert fillet_isolation.server_pid() == before
    drafted = draft_body(body, [face], Plane.XY.offset(10), 3.0)
    assert drafted.volume == pytest.approx(31313.710, abs=1e-3)


def test_analytic_drafts_stay_in_process() -> None:
    """Planes, cylinders and cones meeting along lines and circles: the draft
    golden's box sides, a hub face beside a box blade, a bore."""
    box = Solid.make_box(40, 40, 20)
    sides = [f for f in box.faces() if abs(f.normal_at().Z) < 0.5]
    assert not draft_needs_isolation(box, sides)
    hub = (Pos(0, 0, 10) * Cylinder(22, 20)).rotate(Axis.Z, 180)
    (bladed,) = hub.fuse(Pos(35, 0, 10) * Box(30, 2, 16)).solids()
    (round_face,) = [f for f in bladed.faces() if f.geom_type == GeomType.CYLINDER]
    assert not draft_needs_isolation(bladed, [round_face])
    # ... and a hub face beside the lofted blade does not.
    lofted = _cylinder_hub(180.0)
    assert draft_needs_isolation(lofted, [_round_face(lofted)])


def _snapshot(body: object) -> tuple[object, ...]:
    shape = body  # pyright: ignore[reportAssignmentType]
    vertices = sorted(
        (round(v.X, 9), round(v.Y, 9), round(v.Z, 9))
        for v in shape.vertices()  # pyright: ignore[reportAttributeAccessIssue]
    )
    areas = sorted(f.area for f in shape.faces())  # pyright: ignore[reportAttributeAccessIssue]
    return (shape.volume, len(shape.faces()), len(shape.edges()), vertices, areas)  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize(
    ("build", "plane", "angle"),
    [
        (lambda: _cylinder_hub(180.0), Plane.XY.offset(10), 3.0),
        (lambda: _cone_hub(180.0), Plane.XY, 3.0),
        (lambda: Solid.make_box(40, 40, 20), Plane.XY, 5.0),
    ],
    ids=["cylinder-hub", "cone-hub", "box"],
)
def test_an_isolated_draft_is_the_in_process_draft(
    build: object, plane: Plane, angle: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same volume, topology, face areas and vertices (to 1e-9 mm), and the
    same history, whichever process ran the draft."""

    def run(isolate: bool) -> tuple[tuple[object, ...], list[tuple[int, float]]]:
        def route(_body: object, _faces: object) -> bool:
            return isolate

        monkeypatch.setattr(draft_module, "draft_needs_isolation", route)
        body = build()  # pyright: ignore[reportCallIssue, reportOperatorIssue]
        faces = (
            [_round_face(body)]
            if any(f.geom_type != GeomType.PLANE for f in body.faces())
            else [f for f in body.faces() if abs(f.normal_at().Z) < 0.5]
        )
        history = OpHistory()
        drafted = draft_body(body, faces, plane, angle, history=history)
        assert history.worked_on is not None
        assert len(history.worked_on.faces()) == len(body.faces())
        pairs = [
            (faces.index(source), tilted.area)  # pyright: ignore[reportArgumentType]
            for source, tilted in history.generated
        ]
        return _snapshot(drafted), pairs

    in_process, isolated = run(False), run(True)
    assert isolated == in_process


def test_an_isolated_draft_that_runs_long_is_a_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def slow(*args: object, **kwargs: object) -> object:
        kwargs["wall_seconds"] = 0.0
        return original(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    original = fillet_isolation.run_isolated_draft
    monkeypatch.setattr(draft_module, "run_isolated_draft", slow)
    body = _cylinder_hub(180.0)
    with pytest.raises(DraftTimeoutError):
        draft_body(body, [_round_face(body)], Plane.XY.offset(10), 3.0)

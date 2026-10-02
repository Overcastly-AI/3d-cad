"""Draft isolation (DRAFT-SEGFAULT).

OCCT 7.9.3 SEGFAULTS in ``BRepOffsetAPI_DraftAngle::Build`` on a 30 deg draft
of a hub's cylinder or cone face beside a lofted blade, with the hub's seam at
180 deg (at 0 deg it raises cleanly). In-process that kills the geometry
worker, and so does a -20 deg draft of an all-analytic box wall that a twisted
lofted wedge touches at one vertex. So EVERY draft runs in the blend server
(:mod:`geometry.kernel.fillet_isolation`): the crash costs the draft, and the
result of a draft that builds is the in-process result.
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
from build123d import Face, GeomType, Plane, Polyline, Solid, loft, make_face
from geometry.kernel import draft as draft_module
from geometry.kernel import fillet_isolation
from geometry.kernel.draft import (
    DraftError,
    DraftTimeoutError,
    draft_body,
    draft_needs_isolation,
)
from geometry.kernel.healing import body_is_valid
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


def _wedge_box() -> tuple[Solid, Face]:
    """A 40x30x20 box with a twisted ruled-loft wedge on top, one base corner
    on the box's x=0 top edge, and that x=0 wall: its edges are all lines and
    its neighbours planes, and the wedge's B-spline sides touch it only at
    that vertex (the review's case for 2efdeb6)."""
    base = [(0, 15), (15, 9), (15, 21)]
    top = [(2, 16), (15, 11), (13, 23)]
    wedge = loft(
        [
            make_face(Plane.XY.offset(20) * Polyline(*base, close=True)),
            make_face(Plane.XY.offset(30) * Polyline(*top, close=True)),
        ],
        ruled=True,
    )
    (body,) = Solid.make_box(40, 30, 20).fuse(wedge).clean().solids()
    (wall,) = [
        f
        for f in body.faces()
        if f.geom_type == GeomType.PLANE and abs(f.center().X) < 1e-9
    ]
    return body, wall


def test_every_draft_is_isolated() -> None:
    """No rule on the input is trusted (draft.py): the draft golden's box
    sides run in the server too."""
    box = Solid.make_box(40, 40, 20)
    sides = [f for f in box.faces() if abs(f.normal_at().Z) < 0.5]
    assert draft_needs_isolation(box, sides)


def test_an_analytic_wall_that_crashes_is_a_typed_error() -> None:
    """The wedge-box wall drafted -20 deg segfaulted in-process (exit 139) on
    the analytic route. Isolated, it is a typed outcome and both this
    process and the server carry on."""
    body, wall = _wedge_box()
    assert all(e.geom_type == GeomType.LINE for e in wall.edges())
    try:
        drafted = draft_body(body, [wall], Plane.XY, -20.0)
    except DraftError:
        pass
    else:
        assert body_is_valid(drafted)
    assert fillet_isolation.server_pid() is not None
    # The next draft is served as usual (the wedge wall crashes even at -3 deg;
    # the plain box's wall does not).
    box = Solid.make_box(40, 30, 20)
    (side,) = [f for f in box.faces() if abs(f.center().X) < 1e-9]
    assert draft_body(box, [side], Plane.XY, -3.0).volume > box.volume


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

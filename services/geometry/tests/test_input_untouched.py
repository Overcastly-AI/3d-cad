"""Kernel ops never write to their input body (DRAFT-IN-PLACE and its audit).

OCCT builders can write to the shape they are given: a failed fillet left a
vertex of its input at 74 mm, and a successful draft or sealed shell rewrote
flags of the input's ``TShape`` objects. The input is the caller's body and the
rebuild cache's, so draft and shell run on a working copy
(:mod:`geometry.kernel.working_faces`). For each, after success AND failure:
the input's BRep dump is byte-identical, and a later cut on it gives what a cut
on a fresh build gives.

The blade-hub bodies are the reviewer's (``test_reseam.py``): a QA blade fused
to a cylinder or cone hub, the hub's seam turned 0 or 180 degrees.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false
# pyright: reportAttributeAccessIssue=false

import hashlib
import importlib.util
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from build123d import Cylinder, Face, GeomType, Plane, Pos, Solid
from geometry.kernel.draft import DraftError, draft_body
from geometry.kernel.fillet_guard import max_tolerance
from geometry.kernel.naming import OpHistory
from geometry.kernel.shell import ShellError, shell_body
from geometry.kernel.working_faces import working_copy_faces
from OCP.BRepTools import BRepTools


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


def _dump(body: Solid) -> str:
    """The SHA-256 of *body*'s text BRep: geometry, tolerances, pcurves,
    locations and the TShape flags."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "body.brep"
        assert BRepTools.Write_s(body.wrapped, str(path))
        return hashlib.sha256(path.read_bytes()).hexdigest()


def _blade_cap(body: Solid, z: float) -> Face:
    """The blade's planar end cap at height *z* (2 the root, 18 the tip)."""
    return min(
        (f for f in body.faces() if f.geom_type == GeomType.PLANE),
        key=lambda f: abs(f.center().Z - z) + abs(f.center().X - 36.0),
    )


#: A cut through the hub and the blade, for "a later feature on the input".
_LATER_CUT = Pos(0, 0, 10) * Cylinder(3, 40)
_BLADE_CUT = Pos(30, -3, 10) * Cylinder(1.5, 6)

Build = Callable[[], Solid]
Op = Callable[[Solid], object]

#: (name, body, op, succeeds). Every op here rewrote its input before the fix
#: (success) or must not start to (failure); measured 2026-10-02.
CASES: list[tuple[str, Build, Op, bool]] = [
    (
        "draft cone hub, pull +Z",
        lambda: _cone_hub(180.0),
        lambda b: draft_body(b, [_round_face(b)], Plane.XY.offset(10), 3.0),
        True,
    ),
    (
        "draft cone hub with history",
        lambda: _cone_hub(180.0),
        lambda b: draft_body(
            b, [_round_face(b)], Plane.XY.offset(10), 3.0, history=OpHistory()
        ),
        True,
    ),
    (
        "draft blade tip cap, pull along Y (rewrote a TShape flag)",
        lambda: _cylinder_hub(180.0),
        lambda b: draft_body(b, [_blade_cap(b, 18.0)], Plane.XZ, 3.0),
        True,
    ),
    (
        "draft blade root cap, pull along Y (OCCT builds it invalid)",
        lambda: _cylinder_hub(180.0),
        lambda b: draft_body(b, [_blade_cap(b, 2.0)], Plane.XZ, 3.0),
        False,
    ),
    (
        "draft cylinder hub across its seam (fails)",
        lambda: _cylinder_hub(0.0),
        lambda b: draft_body(b, [_round_face(b)], Plane.XY.offset(10), 3.0),
        False,
    ),
    (
        "sealed shell (rewrote a TShape flag)",
        lambda: _cylinder_hub(0.0),
        lambda b: shell_body(b, [], 1.0),
        True,
    ),
    (
        "open shell",
        lambda: _cone_hub(0.0),
        lambda b: shell_body(b, [max(b.faces(), key=lambda f: f.center().Z)], 1.0),
        True,
    ),
    (
        "shell too thick (fails)",
        lambda: _cone_hub(180.0),
        lambda b: shell_body(b, [max(b.faces(), key=lambda f: f.center().Z)], 30.0),
        False,
    ),
]


@pytest.mark.parametrize(
    ("build", "op", "succeeds"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_the_input_leaves_the_op_as_it_came(
    build: Build, op: Op, succeeds: bool
) -> None:
    body = build()
    before, tolerance = _dump(body), max_tolerance(body)
    if succeeds:
        op(body)
    else:
        with pytest.raises((DraftError, ShellError)):
            op(body)
    assert _dump(body) == before
    assert max_tolerance(body) == tolerance
    fresh = build()
    for tool in (_LATER_CUT, _BLADE_CUT):
        later = body.cut(tool)  # pyright: ignore[reportUnknownMemberType]
        reference = fresh.cut(tool)  # pyright: ignore[reportUnknownMemberType]
        assert later.volume == reference.volume
        assert len(later.faces()) == len(reference.faces())


def test_the_draft_reports_the_callers_faces_and_its_copy() -> None:
    """Names are taken on the caller's faces: the history pairs each picked
    face with its tilted face, and ``worked_on`` is the copy the untouched
    faces of the result come from (the state re-anchors names on it)."""
    body = _cone_hub(180.0)
    picked = _round_face(body)
    history = OpHistory()
    drafted = draft_body(body, [picked], Plane.XY.offset(10), 3.0, history=history)
    ((source, tilted),) = history.generated
    assert source is picked
    assert tilted.geom_type == GeomType.CONE
    assert history.worked_on is not None
    assert history.worked_on is not body
    assert len(history.worked_on.faces()) == len(body.faces())
    assert drafted.volume == pytest.approx(31313.710, abs=1e-3)


def test_the_working_copy_carries_the_picked_faces_over() -> None:
    body = _cone_hub(0.0)
    picked = [body.faces()[3], body.faces()[0]]
    copy, faces = working_copy_faces(body, picked)
    assert [face.center() for face in faces] == [face.center() for face in picked]
    assert all(
        copied.wrapped.Orientation() == face.wrapped.Orientation()
        for copied, face in zip(faces, picked, strict=True)
    )
    assert not any(
        face.wrapped.IsSame(p.wrapped) for face, p in zip(faces, picked, strict=True)
    )
    owned = copy.faces()
    assert all(any(face.wrapped.IsSame(o.wrapped) for o in owned) for face in faces)
    foreign = _cone_hub(0.0).faces()[0]
    assert working_copy_faces(body, [foreign])[1] == [foreign]


def test_two_hubs_drafted_to_one_cone_are_one_body() -> None:
    """The copy changes nothing the user sees. Drafted 3 deg about z = 10, the
    r 22 cylinder hub and the r 24 -> 20 cone hub both become the cone through
    r 22 at z = 10, so the two results are the same solid (31313.710 mm^3,
    measured on the input itself before this change)."""
    cylinder, cone = _cylinder_hub(180.0), _cone_hub(180.0)
    plane = Plane.XY.offset(10)
    a = draft_body(cylinder, [_round_face(cylinder)], plane, 3.0)
    b = draft_body(cone, [_round_face(cone)], plane, 3.0)
    assert a.volume == pytest.approx(31313.710, abs=1e-3)
    assert b.volume == pytest.approx(a.volume, abs=1e-6)
    assert len(a.faces()) == len(b.faces())


def test_a_draft_occt_builds_invalid_is_refused() -> None:
    """OCCT can return an INVALID draft (``BRepCheck``), contrary to what the
    2026-07-13 sweep saw: the blade-root cap of the cylinder hub drafted 3 deg
    with the pull along Y. It is a ``DraftError``, not a body."""
    body = _cylinder_hub(180.0)
    with pytest.raises(DraftError, match="invalid solid"):
        draft_body(body, [_blade_cap(body, 2.0)], Plane.XZ, 3.0)

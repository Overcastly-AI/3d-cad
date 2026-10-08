"""Shell answers in bounded time (SHELL-INTERSECTION-SLOW).

Two bodies took Shell past the gateway's 90 s:

* a 40 x 20 x 10 plate bored r2.991 at (29.171, 9.752) and cross-bored r1.424
  along x at y 11.686, z 6.313, sealed at t 2.39. Arc hollows it right in
  0.16 s; the Intersection join, run only to make a sealed hollow's bytes
  reproducible, took 68 to 133 s. It now runs isolated under a CPU budget, and
  Arc's result ships when it runs out;
* a 240 x 160 x 6 plate with 225 slots (906 faces), opened at the top at t 1:
  OCCT's Arc offset alone takes 77 to 89 s of CPU here (2026-10-02). After it,
  ``offset_history`` paired every result face with every source face (111 s),
  and the wall check classified points on a 1804-edge cavity floor with one
  classifier walking every hole (1.9 s for one face's samples). Those are now
  indexed; the offset itself runs isolated with a CPU budget, and a body whose
  offset runs past it is refused with a typed :class:`ShellTimeout`.

Each fix is checked against what it replaced: the same pairs, the same
classification, Arc's own solid.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportPrivateUsage=false

import io
import random
import time
from typing import Any

import pytest
from build123d import Axis, Box, Compound, Cylinder, Face, Location, Pos, Solid
from geometry.kernel import shell as shell_module
from geometry.kernel.fillet_isolation import CpuMeter, run_isolated
from geometry.kernel.naming import OpHistory
from geometry.kernel.properties import volume_properties
from geometry.kernel.shell import (
    ARC_CPU_SECONDS,
    ARC_OP,
    INTERSECTION_OP,
    ShellError,
    ShellTimeout,
    _OffsetCandidates,
    _offsets_to,
    offset_history,
    shell_body,
)
from geometry.kernel.shell_walls import _EXTREMA_TOL, _InFace
from OCP.BinTools import BinTools
from OCP.BRepTools import BRepTools
from OCP.BRepTopAdaptor import BRepTopAdaptor_FClass2d
from OCP.gp import gp_Pnt2d


def _z_bore(radius: float, x: float, y: float) -> Solid:
    return Cylinder(radius, 200).solids()[0].moved(Location((x, y, 5)))


def _x_bore(radius: float, y: float, z: float) -> Solid:
    return (
        Cylinder(radius, 200).solids()[0].rotate(Axis.Y, 90).moved(Location((20, y, z)))
    )


def _slow_plate() -> Solid:
    """The backlog's body: the Intersection join took 68 to 133 s on it."""
    plate = Box(40, 20, 10).solids()[0].moved(Location((20, 10, 5)))
    bores = [_z_bore(2.991, 29.171, 9.752), _x_bore(1.424, 11.686, 6.313)]
    return plate.cut(*bores).solids()[0]


SLOW_PLATE_T = 2.39


def _slotted_lid(slots: int) -> Solid:
    """A 240 x 160 x 6 plate with *slots* 4 x 6 through slots (tests/
    test_reseam.py's lid; 225 slots is the 906-face lid)."""
    holes = [
        Pos(-110 + 8 * i, -70 + 10 * j, 0) * Box(4, 6, 10)
        for i in range(28)
        for j in range(15)
    ][:slots]
    (solid,) = (Box(240, 160, 6) - Compound(children=holes)).clean().solids()  # pyright: ignore[reportOperatorIssue]
    return solid


def _top(body: Solid) -> list[Face]:
    return [body.faces().sort_by(Axis.Z)[-1]]


# --- the Intersection route runs under a budget ---------------------------------


def test_the_slow_plate_ships_arcs_solid_within_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PERF TRIPWIRE. With a 1 s budget the Intersection build is stopped and
    Arc's solid ships: the right part (it passes the definition check inside
    ``shell_body``), at Arc's volume. Before, this call took 68 to 133 s."""
    monkeypatch.setattr(shell_module, "INTERSECTION_CPU_SECONDS", 1.0)
    body = _slow_plate()
    (arc,) = body.hollow([], -SLOW_PLATE_T).solids()
    start = time.perf_counter()
    shelled = shell_body(body, [], SLOW_PLATE_T)
    spent = time.perf_counter() - start
    assert volume_properties(shelled).volume == pytest.approx(
        volume_properties(arc).volume, rel=1e-9
    )
    assert len(shelled.shells()) == 2
    # 1 s of CPU in the child, plus the blend server's start when it is cold
    # (5-9 s) and a loaded runner's slack.
    assert spent < 40.0, f"shell took {spent:.1f} s"


def test_an_intersection_build_in_budget_still_ships_its_own_bytes() -> None:
    """The budget changes nothing where the build fits in it: a sealed box
    still ships the Intersection join's hollow (no canonical reorder), whose
    outer faces are the input's."""
    body = Solid.make_box(40, 25, 10)
    history = OpHistory()
    shelled = shell_body(body, [], 2.0, history=history)
    worked = history.worked_on
    assert worked is not None
    outer = [
        f
        for f in shelled.faces()
        if any(f.wrapped.IsSame(w.wrapped) for w in worked.faces())
    ]
    assert len(outer) == 6
    assert volume_properties(shelled).volume == pytest.approx(
        40 * 25 * 10 - 36 * 21 * 6
    )


# --- a large body's Arc offset runs isolated, under a budget ----------------------


def test_an_isolated_arc_is_the_in_process_arc(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same solid, and the result's untouched faces are those of the body
    ``history.worked_on`` names (names re-anchor on it)."""
    body = _slotted_lid(6)
    here = shell_body(body, _top(body), 1.0)
    monkeypatch.setattr(shell_module, "ISOLATED_ARC_FACES", 1)
    history = OpHistory()
    isolated = shell_body(body, _top(body), 1.0, history=history)
    assert len(isolated.faces()) == len(here.faces())
    assert volume_properties(isolated).volume == pytest.approx(
        volume_properties(here).volume, rel=1e-12
    )
    worked = history.worked_on
    assert worked is not None
    kept = [
        f
        for f in isolated.faces()
        if any(f.wrapped.IsSame(w.wrapped) for w in worked.faces())
    ]
    assert len(kept) == len(body.faces()) - 1  # all but the opened top
    # The copy keeps the body's face order, which names are carried by.
    assert [tuple(f.center()) for f in worked.faces()] == [
        tuple(f.center()) for f in body.faces()
    ]


def test_an_offset_past_its_budget_is_a_typed_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _slotted_lid(6)
    monkeypatch.setattr(shell_module, "ISOLATED_ARC_FACES", 1)
    monkeypatch.setattr(shell_module, "ARC_WALL_SECONDS", 0.0)
    with pytest.raises(ShellTimeout, match="shell the body before") as refusal:
        shell_body(body, _top(body), 1.0)
    assert isinstance(refusal.value, ShellError)  # the feature's shell_failed


# --- the steps after the offset grow with the faces, not their square -----------


def test_offset_candidates_keep_every_pair_the_exact_test_accepts() -> None:
    """The index only narrows the search: on a slotted lid, a cored block and a
    tube, every source :func:`_offsets_to` accepts for a result face is among
    the candidates."""
    bodies: list[tuple[Solid, list[Face], float]] = []
    lid = _slotted_lid(12)
    bodies.append((lid, _top(lid), 1.0))
    block = Box(40, 30, 20).solids()[0].cut(_z_bore(6, 0, 0)).solids()[0]
    bodies.append((block, _top(block), 2.0))
    tube = Cylinder(10, 20).solids()[0].cut(_z_bore(6, 0, 0)).solids()[0]
    bodies.append((tube, [], 1.0))
    paired = 0
    for body, opened, t in bodies:
        shelled = shell_body(body, opened, t)
        sources = body.faces()
        near = _OffsetCandidates(sources, t)
        for face in shelled.faces():
            exact = [i for i, s in enumerate(sources) if _offsets_to(s, face, t)]
            assert set(exact) <= set(near.of(face))
            paired += bool(exact)
        assert offset_history(body, shelled, t) is not None
    assert paired > 20


def test_offset_history_on_a_slotted_lid_stays_cheap() -> None:
    """PERF TRIPWIRE. On the 246-face lid open at the top at t 1 (791 result
    faces), measured 2026-10-02 under load: OCCT's offset 8.0 s, the pairwise
    ``offset_history`` 9.9 s (1.2 x the offset), the indexed one 0.47 s
    (0.06 x). Both are timed here, so a loaded runner slows both."""
    lid = _slotted_lid(60)
    assert len(lid.faces()) == 246
    start = time.perf_counter()
    (raw,) = lid.hollow(_top(lid), -1.0).solids()
    hollow = time.perf_counter() - start
    start = time.perf_counter()
    offset_history(lid, raw, 1.0)
    history = time.perf_counter() - start
    assert history < 0.25 * hollow, f"history {history:.2f} s, offset {hollow:.2f} s"


def test_a_many_holed_face_classifies_as_one_classifier_does() -> None:
    """:class:`_InFace` against ``BRepTopAdaptor_FClass2d`` at random points of
    the many-holed faces of a slotted lid and of its shell, whose cavity floor
    has rounded hole corners."""
    lid = _slotted_lid(40)
    (shelled,) = lid.hollow(_top(lid), -1.0).solids()
    rng = random.Random(7)
    compared = 0
    for face in [*lid.faces(), *shelled.faces()]:
        split = _InFace(face.wrapped)
        if split._whole is not None:
            continue
        whole = BRepTopAdaptor_FClass2d(face.wrapped, _EXTREMA_TOL)
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(face.wrapped)
        for _ in range(1500):
            uv = gp_Pnt2d(rng.uniform(umin, umax), rng.uniform(vmin, vmax))
            assert split.state(uv) == whole.Perform(uv), (uv.X(), uv.Y())
            compared += 1
    assert compared >= 3000


# --- a multi-lump body takes the same children, on one budget (SHELL-MULTIBODY-HANG)


def _lumps(*solids: Solid) -> Compound:
    """A body of *solids* as separate lumps, 300 mm apart along x."""
    return Compound([s.moved(Location((300 * i, 0, 0))) for i, s in enumerate(solids)])


def _tops(body: Compound) -> list[Face]:
    return [solid.faces().sort_by(Axis.Z)[-1] for solid in body.solids()]


Call = tuple[str, float]


def _spy(monkeypatch: pytest.MonkeyPatch, reported: float | None = None) -> list[Call]:
    """Record each child Shell starts (its op and CPU limit). With *reported*,
    each child that answers is taken to have used that much CPU."""
    calls: list[Call] = []
    real = run_isolated

    def spy(op: str, *args: Any, **kwargs: Any) -> Any:
        calls.append((op, kwargs["cpu_seconds"]))
        out = real(op, *args, **kwargs)
        if reported is not None:
            kwargs["meter"].seconds = reported
        return out

    monkeypatch.setattr(shell_module, "run_isolated", spy)
    return calls


def test_a_lump_takes_the_child_it_would_take_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ROUTE TRIPWIRE. Before, every lump of a multi-lump body was offset
    in-process with no budget (two 906-face lids: 163 s, 2026-10-07). Each lump
    of :data:`ISOLATED_ARC_FACES` faces or more now goes through the child as
    the solid would alone, and a smaller one stays here; the result is the
    in-process one, and ``worked_on`` keeps the body's face order (names
    re-anchor on it)."""
    lid = _slotted_lid(6)  # 30 faces
    body = _lumps(lid, lid, Solid.make_box(40, 25, 10))
    opened = _tops(body)[:2]  # the box lump is sealed
    here = shell_body(body, opened, 1.0)
    monkeypatch.setattr(shell_module, "ISOLATED_ARC_FACES", 30)
    calls = _spy(monkeypatch)
    history = OpHistory()
    isolated = shell_body(body, opened, 1.0, history=history)
    # Both lids through the Arc child; the box in-process, then its sealed
    # Intersection build, which runs isolated whatever the size.
    assert [op for op, _cpu in calls] == [ARC_OP, ARC_OP, INTERSECTION_OP]
    assert len(isolated.solids()) == 3
    assert len(isolated.faces()) == len(here.faces())
    assert volume_properties(isolated).volume == pytest.approx(
        volume_properties(here).volume, rel=1e-12
    )
    worked = history.worked_on
    assert worked is not None and worked is not body
    assert [tuple(f.center()) for f in worked.faces()] == [
        tuple(f.center()) for f in body.faces()
    ]
    kept = [
        f
        for f in isolated.faces()
        if any(f.wrapped.IsSame(w.wrapped) for w in worked.faces())
    ]
    assert len(kept) == len(body.faces()) - 2  # all but the two opened tops


def test_the_arc_budget_is_the_whole_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ROUTE TRIPWIRE: three isolated lumps share one 40 s budget, not 3 x
    40 s. Each child is taken to report 30 s of CPU: the second gets the 10 s
    left as its limit, and the third is refused without a child."""
    lid = _slotted_lid(6)
    body = _lumps(lid, lid, lid)
    monkeypatch.setattr(shell_module, "ISOLATED_ARC_FACES", 1)
    calls = _spy(monkeypatch, reported=30.0)
    with pytest.raises(ShellTimeout, match="shell the body before"):
        shell_body(body, _tops(body), 1.0)
    assert calls == [(ARC_OP, ARC_CPU_SECONDS), (ARC_OP, ARC_CPU_SECONDS - 30.0)]


def test_lumps_offset_here_are_charged_to_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Small lumps stay in-process (byte-identical to before), but the CPU they
    take is charged: once it is spent the next lump is refused, so many
    medium lumps cannot add up to a hang either."""
    lid = _slotted_lid(6)
    body = _lumps(lid, lid)
    monkeypatch.setattr(shell_module, "ARC_CPU_SECONDS", 1e-3)
    calls = _spy(monkeypatch)
    with pytest.raises(ShellTimeout):
        shell_body(body, _tops(body), 1.0)
    assert calls == []


def test_a_multi_lump_offset_past_its_budget_is_a_typed_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real child, really stopped: two 246-face lids each take about 5 s of
    CPU to offset; with a 1 s budget the first child is stopped by its CPU
    limit and the second never starts."""
    lid = _slotted_lid(60)
    body = _lumps(lid, lid)
    monkeypatch.setattr(shell_module, "ISOLATED_ARC_FACES", 1)
    monkeypatch.setattr(shell_module, "ARC_CPU_SECONDS", 1.0)
    calls = _spy(monkeypatch)
    start = time.perf_counter()
    with pytest.raises(ShellTimeout, match="492-face body") as refusal:
        shell_body(body, _tops(body), 1.0)
    spent = time.perf_counter() - start
    assert isinstance(refusal.value, ShellError)  # the feature's shell_failed
    assert calls == [(ARC_OP, 1.0)]
    # 1-2 s of CPU in the child, the server's cold start (5-9 s), slack.
    assert spent < 40.0, f"shell took {spent:.1f} s"


def test_one_slow_lump_leaves_the_others_their_own_intersection_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plate whose Intersection build runs out its budget, beside a box:
    the box still gets a whole build's budget and ships the bytes it ships
    beside a quick lump, and the plate ships Arc's result. The two children
    together stay within :data:`INTERSECTION_BUILDS` builds' budgets."""
    monkeypatch.setattr(shell_module, "INTERSECTION_CPU_SECONDS", 1.0)
    box = Solid.make_box(10, 10, 10).moved(Location((300, 0, 0)))
    plate = _slow_plate()
    (arc,) = plate.hollow([], -SLOW_PLATE_T).solids()
    calls = _spy(monkeypatch)
    shelled = shell_body(Compound([plate, box]), [], SLOW_PLATE_T)
    assert calls == [(INTERSECTION_OP, 1.0), (INTERSECTION_OP, 1.0)]
    quick = Solid.make_box(40, 20, 10)  # the plate's envelope, unbored
    beside_quick = shell_body(Compound([quick, box]), [], SLOW_PLATE_T)
    lumps = sorted(shelled.solids(), key=lambda s: s.center().X)
    assert _bytes(lumps[1]) == _bytes(beside_quick.solids()[1])
    assert volume_properties(lumps[0]).volume == pytest.approx(
        volume_properties(arc).volume, rel=1e-9
    )
    assert len(shelled.shells()) == 4  # each lump sealed: skin and cavity


def test_a_child_reports_only_its_own_cpu() -> None:
    """The child's count starts at its fork: a child that sleeps reports next
    to nothing, not the server's own start-up (seconds of imports)."""
    meter = CpuMeter()
    run_isolated("probe-sleep", Solid.make_box(1, 1, 1), [], 0.3, None, meter=meter)
    assert meter.seconds is not None
    assert meter.seconds < 0.2


def _bytes(shape: Solid | Compound) -> bytes:
    sink = io.BytesIO()
    BinTools.Write_s(shape.wrapped, sink)
    return sink.getvalue()

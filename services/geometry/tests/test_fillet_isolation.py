"""Blend isolation (:mod:`geometry.kernel.fillet_isolation`).

OCCT's fillet SEGFAULTS on the root edges of a box whose face is tangent to a
torus's outer equator (FILLET-TORUS-SEGFAULT). In-process that kills the
geometry worker; isolated, it must cost only the fillet: a typed error, and this
process (and its blend server) carry on.
"""

import functools
import math
import os
import signal
import subprocess
import sys
import textwrap

import pytest
from build123d import Align, Axis, Box, Compound, Edge, GeomType, Location, Solid
from geometry.kernel import fillet as fillet_module
from geometry.kernel import fillet_isolation
from geometry.kernel.fillet import FilletError, FilletTimeoutError, fillet_body
from geometry.kernel.fillet_isolation import (
    BlendTimedOut,
    needs_isolation,
    run_isolated,
    server_pid,
    working_copy,
)
from geometry.kernel.naming import OpHistory

_TORUS_CASE = """
from build123d import Align, Box, GeomType, Location, Solid
body = Solid.make_torus(20, 6) + Box(
    4, 2, 30, align=(Align.MIN, Align.CENTER, Align.CENTER)
).moved(Location((22, 0, 0)))
edges = [
    e
    for f in body.faces()
    if f.geom_type == GeomType.TORUS
    for e in f.edges()
    if e.geom_type != GeomType.CIRCLE
]
"""


def _torus_with_tangent_box() -> tuple[Solid, list[Edge]]:
    """A Ø52 torus (R20 r6) and a 4x2x30 box from x=22, whose x=26 face
    touches the torus's outer equator: the eight B-spline root edges."""
    body = Solid.make_torus(20, 6) + Box(
        4, 2, 30, align=(Align.MIN, Align.CENTER, Align.CENTER)
    ).moved(Location((22, 0, 0)))
    assert isinstance(body, Solid)
    edges = [
        e
        for f in body.faces()
        if f.geom_type == GeomType.TORUS
        for e in f.edges()
        if e.geom_type != GeomType.CIRCLE
    ]
    assert len(edges) == 8
    return body, edges


def _signature(shape: Solid | Compound) -> tuple[float, int, int, int, list[float]]:
    """Volume, topology counts and every face's area, in explorer order."""
    return (
        shape.volume,
        len(shape.faces()),
        len(shape.edges()),
        len(shape.vertices()),
        [face.area for face in shape.faces()],
    )


def _position(edges: list[Edge], source: object) -> int:
    return next(i for i, edge in enumerate(edges) if edge is source)


def _same(a: object, b: object) -> bool:
    return bool(a.IsSame(b))  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownArgumentType]


def _always(_body: object, _edges: object) -> bool:
    return True


def test_the_crash_is_still_in_occt() -> None:
    """The defect the isolation exists for: the plain fillet kills its
    process with SIGSEGV. If an OCCT upgrade fixes it, this says so."""
    script = _TORUS_CASE + "body.fillet(1.0, edges)\n"
    done = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == -signal.SIGSEGV, done.stderr[-2000:]


def test_a_crashing_fillet_is_a_typed_error_and_the_process_survives() -> None:
    body, edges = _torus_with_tangent_box()
    assert needs_isolation(body, edges)
    pid = os.getpid()
    with pytest.raises(FilletError, match="crashed") as caught:
        fillet_body(body, edges, 1.0, history=OpHistory())
    assert not isinstance(caught.value, FilletTimeoutError)
    assert os.getpid() == pid
    # Only the forked child died: the warm server is still up and serving.
    server = server_pid()
    assert server is not None
    box = Solid.make_box(40, 25, 10)
    tall = list(box.edges().filter_by(Axis.Z))
    copy, _edges, solids = run_isolated("fillet", box, tall, 2.0, None)
    assert server_pid() == server
    assert copy.volume == pytest.approx(10_000.0)
    # Four R2 rounds of the 10 mm tall edges: each removes (r^2 - pi r^2 / 4) h.
    rounded = 10_000 - 4 * (4 - math.pi) * 10
    assert sum(s.volume for s in solids) == pytest.approx(rounded, rel=1e-9)


def test_an_analytic_fillet_stays_in_process() -> None:
    box = Solid.make_box(40, 25, 10)
    assert not needs_isolation(box, list(box.edges()))
    cylinder = Solid.make_cylinder(10, 20)
    assert not needs_isolation(cylinder, list(cylinder.edges()))


def test_an_isolated_fillet_is_the_in_process_fillet() -> None:
    """Shapes cross as exact binary BRep: the same input gives the same solid
    either way (exact volume, topology and face areas; the BRep text differs
    only in the order of pcurve tables and the sign of a zero), and the
    history names the same faces."""
    body = Solid.make_torus(20, 6) + Box(
        5, 2, 30, align=(Align.MIN, Align.CENTER, Align.CENTER)
    ).moved(Location((22, 0, 0)))
    assert isinstance(body, Solid)
    edges = [e for e in body.edges() if e.geom_type == GeomType.BSPLINE]
    assert needs_isolation(body, edges)
    work, work_edges = working_copy(body, edges)
    local = OpHistory()
    expected = fillet_module._fillet(work, work_edges, 1.0, local)  # pyright: ignore[reportPrivateUsage]
    isolated = OpHistory()
    copy, moved, solids = run_isolated("fillet", body, edges, 1.0, isolated)
    assert [_signature(s) for s in solids] == [_signature(s) for s in expected]
    assert _signature(copy) == _signature(work)
    assert len(isolated.generated) == len(local.generated) > 0
    for (source, face), (local_source, local_face) in zip(
        isolated.generated, local.generated, strict=True
    ):
        assert _position(moved, source) == _position(work_edges, local_source)
        assert face.area == local_face.area
    # The result's untouched faces ARE the returned copy's (names re-anchor).
    kept = [k.wrapped for k in copy.faces()]
    assert any(
        _same(face.wrapped, k)  # pyright: ignore[reportUnknownArgumentType]
        for face in solids[0].faces()
        for k in kept
    )


def test_a_hung_blend_is_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    body = Solid.make_box(40, 25, 10)
    edges = list(body.edges().filter_by(Axis.Z))
    with pytest.raises(BlendTimedOut):
        run_isolated("fillet", body, edges, 2.0, None, wall_seconds=0.0)
    monkeypatch.setattr(fillet_module, "needs_isolation", _always)
    monkeypatch.setattr(
        fillet_module,
        "run_isolated",
        functools.partial(fillet_isolation.run_isolated, wall_seconds=0.0),
    )
    with pytest.raises(FilletTimeoutError, match="time limit"):
        fillet_body(body, edges, 2.0)
    # The server answered "timeout" for its child; it was not replaced.
    assert server_pid() is not None

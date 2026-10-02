"""Run a risky edge blend (fillet or chamfer) where a crash cannot reach the service.

WHY. OCCT's blend (``ChFi3d``, under both ``BRepFilletAPI_MakeFillet`` and
``BRepFilletAPI_MakeChamfer``) can SEGFAULT, not raise: an R1 fillet of the
edges where a 4 mm box meets a ``make_torus(20, 6)`` with one box face tangent
to the torus's outer equator kills the process inside ``BRepFilletAPI_MakeFillet``
(FILLET-TORUS-SEGFAULT, OCCT 7.9.3). In-process, that takes down the geometry
worker and every request it is serving. No pre-check predicts it: the input is
``BRepCheck``-valid, the same edges at a 5 mm box width fillet fine, and two of
the eight edges alone fail cleanly. So the guard is isolation, and the question
is only what it costs.

WHAT RUNS WHERE. :func:`needs_isolation` is a cheap, pure test of the input:

* in-process (unchanged, byte-identical): every rounded edge is a line, circle
  or ellipse and every face beside it is a plane, cylinder, cone or sphere.
  These are the blends OCCT builds in closed form (``ChFiKPart``) or walks on
  quadrics, i.e. nearly every machined-part fillet;
* isolated: anything else (an intersection B-spline, a torus, a free-form
  face). The torus crash is in this class.

Because the test is a function of the input alone, the same tree always takes
the same path (RESEARCH §9).

HOW. One warm server per service process (``python -m
geometry.kernel._fillet_worker``), started on first use (or at boot, setting
``BLEND_SERVER_PREWARM``), imports the kernel once. Per blend it FORKS a fresh
child (it is single-threaded, so the fork is safe, unlike forking the threaded
service), which does the blend under a CPU ceiling. Each call has its own two
socket pairs, handed to the server over its control socket: DATA (request and
reply, shared with the child) and STATUS (the server reports the child's pid,
then how it ended). The caller enforces the wall clock itself by killing that
pid, so no lock is held while a blend runs and blends run concurrently. A
crash or an overrun kills only that child; the next blend forks again at no
start-up cost. Shapes cross as OCCT binary BRep (``BinTools``, exact doubles):
the body and its edges in one compound, and back the body, its edges, the
result and the generated faces in one compound, so the result's untouched faces
ARE the returned body's (names re-anchor on it as on any working copy).

LIFECYCLE. A child dies with the server (``PR_SET_PDEATHSIG``), and the server,
when its control socket closes, kills and reaps its children before it exits.
A server found dead is dropped and replaced; closing one twice is a no-op (it
owns socket objects, never bare descriptor numbers). In a container, run the
service under an init (compose ``init: true``) so nothing orphaned by a killed
server outlives it as a zombie: uvicorn as PID 1 reaps no one.

Cost (measured 2026-10-01, 4-core sandbox): see ``docs/RESEARCH.md``
"Blend isolation".
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false, reportUnknownParameterType=false

import atexit
import contextlib
import io
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from typing import Any

from build123d import Compound, Edge, Face, Solid
from OCP.BinTools import BinTools, BinTools_FormatVersion
from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.GeomAbs import (
    GeomAbs_Circle,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Ellipse,
    GeomAbs_Line,
    GeomAbs_Plane,
    GeomAbs_Sphere,
)
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Iterator, TopoDS_Shape
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

from geometry.kernel.naming import OpHistory
from geometry.kernel.types import BodyShape

#: CPU seconds one isolated blend may burn before it is killed (``RLIMIT_CPU``
#: in the forked child: invariant to machine load, like the STEP parse bound).
#: The blends measured for it take 70-500 ms.
BLEND_CPU_SECONDS = 60.0
#: Wall-clock backstop for a child that is wedged rather than computing.
BLEND_WALL_SECONDS = 180.0
#: How long the server may take to start (it imports the kernel once).
_START_SECONDS = 120.0

_SAFE_CURVES = frozenset({GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse})
_SAFE_SURFACES = frozenset(
    {GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere}
)


class BlendFailed(RuntimeError):
    """The isolated blend raised (OCCT's ordinary, clean failure)."""


class BlendCrashed(RuntimeError):
    """The isolated blend killed its process (a signal, not an exception)."""


class BlendTimedOut(RuntimeError):
    """The isolated blend exceeded its CPU or wall-clock bound."""


def working_copy(
    body: BodyShape, edges: Sequence[Edge]
) -> tuple[BodyShape, list[Edge]]:
    """A topology copy of *body* (geometry shared, so the result is the same
    numbers) and *edges* on it, for OCCT to blend IN PLACE (fillet, chamfer):
    a failed blend can leave its input's vertices at any tolerance."""
    copier = BRepBuilderAPI_Copy(body.wrapped, False, False)
    copy = type(body)(copier.Shape())
    return copy, [Edge(copier.ModifiedShape(edge.wrapped)) for edge in edges]


def needs_isolation(body: BodyShape, edges: Sequence[Edge]) -> bool:
    """Whether blending *edges* of *body* leaves OCCT's analytic cases (module
    docstring): an edge that is not a line/circle/ellipse, or a face beside one
    that is not a plane/cylinder/cone/sphere."""
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(body.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
    for edge in edges:
        if BRepAdaptor_Curve(edge.wrapped).GetType() not in _SAFE_CURVES:
            return True
        if not ancestors.Contains(edge.wrapped):
            return True  # not an edge of the body: let the kernel say so, isolated
        for face in ancestors.FindFromKey(edge.wrapped):
            surface = BRepAdaptor_Surface(TopoDS.Face_s(face), False)
            if surface.GetType() not in _SAFE_SURFACES:
                return True
    return False


def run_isolated(
    op: str,
    body: BodyShape,
    edges: Sequence[Edge],
    size_mm: float,
    history: OpHistory | None,
    *,
    cpu_seconds: float = BLEND_CPU_SECONDS,
    wall_seconds: float = BLEND_WALL_SECONDS,
) -> tuple[BodyShape, list[Edge], list[Solid]]:
    """Blend *edges* of *body* (``op`` is ``"fillet"`` or ``"chamfer"``) in a
    forked child of the warm server.

    Returns ``(body', edges', solids)``: *body'* is a copy of *body* the result
    was built on (its untouched faces are the result's), *edges'* the edges on
    it, in order. *history*, when given, receives ``(edge', face)`` pairs.

    Raises:
        BlendFailed: the kernel raised (as the in-process call would have).
        BlendCrashed: the blend killed its process.
        BlendTimedOut: it ran past *cpu_seconds* of CPU or *wall_seconds*.
    """
    header = {
        "op": op,
        "size": size_mm,
        "history": history is not None,
        "kind": type(body).__name__,
        "cpu": cpu_seconds,
    }
    blob = write_shapes([body.wrapped, *(edge.wrapped for edge in edges)])
    reply, data = _call(header, blob, wall_seconds)
    if reply.get("status") != "ok":
        raise BlendFailed(str(reply.get("error", "unknown")))
    parts = read_shapes(data)
    copy: BodyShape = (Solid if header["kind"] == "Solid" else Compound)(parts[0])
    count = len(edges)
    moved = [Edge(TopoDS.Edge_s(shape)) for shape in parts[1 : 1 + count]]
    solids = [Solid(shape) for shape in _children(parts[1 + count])]
    if history is not None:
        faces = _children(parts[2 + count])
        for index, face in zip(reply["generated"], faces, strict=True):
            history.generated.append((moved[index], Face(TopoDS.Face_s(face))))
    return copy, moved, solids


# --- the wire: frames of (JSON header, binary BRep) ---------------------------------


def write_shapes(shapes: Sequence[TopoDS_Shape]) -> bytes:
    """*shapes* as one binary BRep compound (shared subshapes kept shared)."""
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    sink = io.BytesIO()
    # No triangulation: a blend input carries none in-process either (the
    # working copy is made with copyMesh=False).
    BinTools.Write_s(
        compound,
        sink,
        False,
        False,
        BinTools_FormatVersion.BinTools_FormatVersion_CURRENT,
    )
    return sink.getvalue()


def read_shapes(data: bytes) -> list[TopoDS_Shape]:
    """The shapes :func:`write_shapes` wrote, in order."""
    compound = TopoDS_Shape()
    BinTools.Read_s(compound, io.BytesIO(data))
    return _children(compound)


def make_compound(shapes: Sequence[TopoDS_Shape]) -> TopoDS_Compound:
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def _children(shape: TopoDS_Shape) -> list[TopoDS_Shape]:
    out: list[TopoDS_Shape] = []
    it = TopoDS_Iterator(shape)
    while it.More():
        out.append(it.Value())
        it.Next()
    return out


_LENGTHS = struct.Struct("<IQ")


def encode_frame(header: dict[str, Any], data: bytes = b"") -> bytes:
    text = json.dumps(header).encode()
    return _LENGTHS.pack(len(text), len(data)) + text + data


def _recv_exact(
    sock: socket.socket, size: int, deadline: float | None
) -> bytearray | None:
    """Exactly *size* bytes from *sock*, into one preallocated buffer; ``None``
    at EOF. Raises :class:`TimeoutError` at *deadline* (``time.monotonic``)."""
    buffer = bytearray(size)
    view = memoryview(buffer)
    got = 0
    while got < size:
        if deadline is None:
            sock.settimeout(None)
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            sock.settimeout(remaining)
        count = sock.recv_into(view[got:])  # socket.timeout is TimeoutError
        if count == 0:
            return None
        got += count
    return buffer


def recv_frame(
    sock: socket.socket, deadline: float | None
) -> tuple[dict[str, Any], bytes] | None:
    """One frame from *sock*; ``None`` at EOF (a partial frame included).
    Raises :class:`TimeoutError` at *deadline*."""
    lengths = _recv_exact(sock, _LENGTHS.size, deadline)
    if lengths is None:
        return None
    head, size = _LENGTHS.unpack(lengths)
    body = _recv_exact(sock, head + size, deadline)
    if body is None:
        return None
    return json.loads(bytes(body[:head])), bytes(body[head:])


def send_frame(sock: socket.socket, header: dict[str, Any], data: bytes = b"") -> None:
    sock.settimeout(None)
    sock.sendall(encode_frame(header, data))


# --- one call: hand two socket pairs to the server, then wait without a lock --------

#: How long the server may take to report a child it forked or reaped.
_REAP_SECONDS = 30.0


def _call(
    header: dict[str, Any], data: bytes, wall_seconds: float
) -> tuple[dict[str, Any], bytes]:
    """The child's reply frame. Raises :class:`BlendCrashed` /
    :class:`BlendTimedOut` when the child could not give one."""
    deadline = time.monotonic() + wall_seconds
    server = _current()
    op = str(header.get("op"))
    mine, theirs = socket.socketpair()
    status, status_theirs = socket.socketpair()
    with mine, status:
        try:
            server.hand_over(theirs, status_theirs)
        except OSError as exc:
            _discard(server)
            raise BlendCrashed("the blend server went away") from exc
        finally:
            theirs.close()
            status_theirs.close()
        try:
            started = recv_frame(status, time.monotonic() + _REAP_SECONDS)
        except TimeoutError as exc:
            _discard(server)  # it did not even fork: replace it
            raise BlendTimedOut(op) from exc
        if started is None:
            _discard(server)
            raise BlendCrashed("the blend server went away")
        pid = int(started[0]["pid"])
        reply: tuple[dict[str, Any], bytes] | None = None
        timed_out = False
        try:
            send_frame(mine, header, data)
            reply = recv_frame(mine, deadline)
        except TimeoutError:
            timed_out = True
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        except OSError:
            reply = None  # the child died before it read or answered
        try:
            ended = recv_frame(status, time.monotonic() + _REAP_SECONDS)
        except TimeoutError:
            ended = None
    if timed_out:
        raise BlendTimedOut(op)
    if ended is None:
        _discard(server)
        raise BlendCrashed("the blend server went away")
    sig = int(ended[0].get("signal", 0))
    if sig in (signal.SIGXCPU, signal.SIGKILL):  # RLIMIT_CPU, soft then hard
        raise BlendTimedOut(op)
    if sig or reply is None or int(ended[0].get("exit", 1)) != 0:
        raise BlendCrashed(f"signal {sig}")
    return reply


# --- the warm server, one per service process --------------------------------------

#: How long a server may take to stop its children and exit when closed.
_STOP_SECONDS = 5.0


class _Server:
    """The ``_fillet_worker`` server process and its control socket."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.pid = os.getpid()
        control, theirs = socket.socketpair()
        self._control: socket.socket | None = control
        env = dict(os.environ)
        # The server forks per blend: keep it single-threaded (BLAS pools).
        env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        try:
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "geometry.kernel._fillet_worker",
                    str(theirs.fileno()),
                ],
                pass_fds=(theirs.fileno(),),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        finally:
            theirs.close()
        self.child_pid = self._process.pid
        try:
            ready = recv_frame(control, time.monotonic() + _START_SECONDS)
        except OSError:  # TimeoutError included
            ready = None
        if ready is None or ready[0].get("status") != "ready":
            self.close()
            raise BlendCrashed("the blend server did not start")

    def alive(self) -> bool:
        return self._control is not None and self._process.poll() is None

    def hand_over(self, data: socket.socket, status: socket.socket) -> None:
        """Pass one call's two sockets to the server, which forks the child."""
        with self._lock:
            if self._control is None:
                raise OSError("the blend server is closed")
            self._control.settimeout(None)
            socket.send_fds(self._control, [b"c"], [data.fileno(), status.fileno()])

    def close(self) -> None:
        """Stop the server; idempotent. Closing its control socket lets it kill
        and reap its children first; it is killed if it does not exit."""
        with self._lock:
            control, self._control = self._control, None
        if control is None:
            return
        control.close()
        try:
            self._process.wait(timeout=_STOP_SECONDS)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()


class _Slot:
    """This process's server (``None`` until the first isolated blend)."""

    server: _Server | None = None


#: Held only to start or replace the server, never while a blend runs.
_START_LOCK = threading.Lock()
_SLOT = _Slot()


def _current() -> _Server:
    """This process's live server, started (or replaced) if need be."""
    with _START_LOCK:
        server = _SLOT.server
        if server is not None and server.pid == os.getpid() and server.alive():
            return server
        _SLOT.server = None
        if server is not None and server.pid == os.getpid():
            server.close()
        server = _SLOT.server = _Server()
        return server


def _discard(server: _Server) -> None:
    """Drop *server* (found dead or wedged) so the next call starts another."""
    with _START_LOCK:
        if _SLOT.server is server:
            _SLOT.server = None
    server.close()


def prewarm() -> None:
    """Start this process's server now, in the background
    (``BLEND_SERVER_PREWARM``); the first non-analytic blend then skips the
    5-9 s start."""

    def start() -> None:
        with contextlib.suppress(BlendCrashed):
            _current()

    threading.Thread(target=start, name="blend-server-prewarm", daemon=True).start()


def shutdown() -> None:
    """Stop this process's blend server, if it has one (tests, shutdown)."""
    with _START_LOCK:
        server, _SLOT.server = _SLOT.server, None
    if server is not None and server.pid == os.getpid():
        server.close()


atexit.register(shutdown)


def server_pid() -> int | None:
    """The running blend server's pid (tests)."""
    with _START_LOCK:
        server = _SLOT.server
        if server is None or not server.alive():
            return None
        return server.child_pid

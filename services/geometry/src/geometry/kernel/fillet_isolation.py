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
geometry.kernel._fillet_worker``), started on first use, imports the kernel
once. Per blend it FORKS a fresh child (it is single-threaded, so the fork is
safe, unlike forking the threaded service), which does the blend under a CPU
ceiling and writes the result back. A crash or a CPU/wall overrun kills only
that child, and the server reports it; the next blend forks again at no
start-up cost. Shapes cross as OCCT binary BRep (``BinTools``, exact doubles):
the body and its edges in one compound, and back the body, its edges, the
result and the generated faces in one compound, so the result's untouched faces
ARE the returned body's (names re-anchor on it as on any working copy).

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
import select
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
        "wall": wall_seconds,
    }
    blob = write_shapes([body.wrapped, *(edge.wrapped for edge in edges)])
    reply, data = _server().call(header, blob, wall_seconds + 30.0)
    status = reply.get("status")
    if status == "crashed":
        raise BlendCrashed(f"signal {reply.get('signal')}")
    if status == "timeout":
        raise BlendTimedOut(op)
    if status != "ok":
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


def encode_frame(header: dict[str, Any], data: bytes) -> bytes:
    text = json.dumps(header).encode()
    return _LENGTHS.pack(len(text), len(data)) + text + data


def decode_frame(frame: bytes) -> tuple[dict[str, Any], bytes] | None:
    """The frame at the start of *frame*, or ``None`` if it is incomplete."""
    if len(frame) < _LENGTHS.size:
        return None
    head, size = _LENGTHS.unpack_from(frame)
    start = _LENGTHS.size + head
    if len(frame) < start + size:
        return None
    return json.loads(frame[_LENGTHS.size : start]), frame[start : start + size]


def read_frame(fd: int, deadline: float | None) -> tuple[dict[str, Any], bytes] | None:
    """One frame from *fd*; ``None`` at EOF. Raises :class:`TimeoutError` at
    *deadline* (``time.monotonic``)."""
    buffer = bytearray()
    while True:
        frame = decode_frame(bytes(buffer))
        if frame is not None:
            return frame
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                raise TimeoutError
        chunk = os.read(fd, 1 << 20)
        if not chunk:
            return None
        buffer += chunk


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


# --- the warm server, one per service process --------------------------------------


class _Server:
    """The ``_fillet_worker`` server process and its two pipes."""

    def __init__(self) -> None:
        to_child, self._requests = os.pipe()
        self._replies, from_child = os.pipe()
        env = dict(os.environ)
        # The server forks per blend: keep it single-threaded (BLAS pools).
        env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "geometry.kernel._fillet_worker",
                str(to_child),
                str(from_child),
            ],
            pass_fds=(to_child, from_child),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        os.close(to_child)
        os.close(from_child)
        self.pid = os.getpid()
        self.child_pid = self._process.pid
        try:
            ready = read_frame(self._replies, time.monotonic() + _START_SECONDS)
        except TimeoutError:
            ready = None
        if ready is None or ready[0].get("status") != "ready":
            self.close()
            raise BlendCrashed("the blend server did not start")

    def alive(self) -> bool:
        return self._process.poll() is None

    def call(
        self, header: dict[str, Any], data: bytes, backstop_s: float
    ) -> tuple[dict[str, Any], bytes]:
        try:
            write_all(self._requests, encode_frame(header, data))
            reply = read_frame(self._replies, time.monotonic() + backstop_s)
        except TimeoutError as exc:
            self.close()  # the server itself is wedged: replace it
            raise BlendTimedOut(str(header.get("op"))) from exc
        except OSError as exc:
            self.close()
            raise BlendCrashed("the blend server went away") from exc
        if reply is None:
            self.close()
            raise BlendCrashed("the blend server went away")
        return reply

    def close(self) -> None:
        for fd in (self._requests, self._replies):
            with contextlib.suppress(OSError):
                os.close(fd)
        if self._process.poll() is None:
            self._process.kill()
        self._process.wait()


class _Slot:
    """This process's server (``None`` until the first isolated blend)."""

    server: _Server | None = None


_LOCK = threading.Lock()
_SLOT = _Slot()


class _Lease:
    """The process's server, held under the lock for one call."""

    def call(
        self, header: dict[str, Any], data: bytes, backstop_s: float
    ) -> tuple[dict[str, Any], bytes]:
        with _LOCK:
            server = _SLOT.server
            if server is None or server.pid != os.getpid() or not server.alive():
                if server is not None and server.pid == os.getpid():
                    server.close()
                server = _SLOT.server = _Server()
            return server.call(header, data, backstop_s)


def _server() -> _Lease:
    return _Lease()


def shutdown() -> None:
    """Stop this process's blend server, if it has one (tests, shutdown)."""
    with _LOCK:
        server, _SLOT.server = _SLOT.server, None
        if server is not None and server.pid == os.getpid():
            server.close()


atexit.register(shutdown)


def server_pid() -> int | None:
    """The running blend server's pid (tests)."""
    with _LOCK:
        server = _SLOT.server
        if server is None or not server.alive():
            return None
        return server.child_pid

"""The warm blend server: forks a fresh child per fillet/chamfer (see
:mod:`geometry.kernel.fillet_isolation`, which starts and talks to it).

Run as ``python -m geometry.kernel._fillet_worker <control fd>``. It imports the
kernel ONCE and says ``ready`` on its control socket. Each call then arrives as
two sockets passed over it (``SCM_RIGHTS``): DATA and STATUS. The server forks a
child that reads the request from DATA, blends under ``RLIMIT_CPU`` and writes
the reply to DATA; the server writes the child's pid to STATUS, and, once it has
reaped the child, how it ended (exit code or signal). The server never waits on
a child, so calls run concurrently; the CALLER enforces the wall clock by
killing the pid. The server stays single-threaded (so forking it is safe).

LIFECYCLE. A child is killed if the server dies (``PR_SET_PDEATHSIG``). When the
control socket closes (the service went away or closed it) the server kills and
reaps every child before it exits, so it leaves nothing for PID 1 to reap.

The sockets are dedicated descriptors, not stdout: OCCT prints to stdout.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false

import contextlib
import ctypes
import math
import os
import select
import signal
import socket
import sys
import time
from typing import Any

from build123d import Compound, Edge, Solid
from OCP.TopoDS import TopoDS

from geometry.kernel.chamfer import _chamfer  # pyright: ignore[reportPrivateUsage]
from geometry.kernel.fillet import _fillet  # pyright: ignore[reportPrivateUsage]
from geometry.kernel.fillet_isolation import (
    encode_frame,
    make_compound,
    read_shapes,
    recv_frame,
    send_frame,
    write_shapes,
)
from geometry.kernel.naming import OpHistory


def _probe_sleep(
    _body: object, _edges: object, seconds: float, _history: object
) -> list[Solid]:
    """Not a blend: a child that takes *seconds*, the stand-in the tests use
    for a hung blend (a real one cannot be produced on demand)."""
    time.sleep(seconds)
    return []


_OPS: dict[str, Any] = {
    "fillet": _fillet,
    "chamfer": _chamfer,
    "probe-sleep": _probe_sleep,
}

#: ``prctl(PR_SET_PDEATHSIG, ...)``: Linux's "signal me when my parent dies".
_PR_SET_PDEATHSIG = 1


def _blend(header: dict[str, Any], data: bytes) -> bytes:
    """The reply frame for one request (runs in the forked child)."""
    try:
        parts = read_shapes(data)
        body = (Solid if header["kind"] == "Solid" else Compound)(parts[0])
        edges = [Edge(TopoDS.Edge_s(shape)) for shape in parts[1:]]
        history = OpHistory() if header["history"] else None
        solids = _OPS[header["op"]](body, edges, float(header["size"]), history)
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        return encode_frame({"status": "failed", "error": type(exc).__name__})
    index = {id(edge): i for i, edge in enumerate(edges)}
    generated = [] if history is None else history.generated
    shapes = [
        body.wrapped,
        *(edge.wrapped for edge in edges),
        make_compound([solid.wrapped for solid in solids]),
        make_compound([face.wrapped for _source, face in generated]),
    ]
    reply = {
        "status": "ok",
        "generated": [index[id(source)] for source, _face in generated],
    }
    return encode_frame(reply, write_shapes(shapes))


def _child(data: socket.socket, server_pid: int) -> None:
    """The forked child: die with the server, then serve one request."""
    with contextlib.suppress(OSError, AttributeError):
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
    if os.getppid() != server_pid:  # the server died before prctl took
        return
    import resource

    request = recv_frame(data, None)
    if request is None:
        return
    header, payload = request
    soft = max(1, math.ceil(float(header["cpu"])))
    resource.setrlimit(resource.RLIMIT_CPU, (soft, soft + 1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    data.settimeout(None)
    data.sendall(_blend(header, payload))


def _fork(
    control: socket.socket, wake: int, data: socket.socket, status: socket.socket
) -> int:
    server_pid = os.getpid()
    pid = os.fork()
    if pid == 0:
        code = 1
        try:
            signal.set_wakeup_fd(-1)
            signal.signal(signal.SIGCHLD, signal.SIG_DFL)
            control.close()
            status.close()
            os.close(wake)
            _child(data, server_pid)
            code = 0
        except BaseException:
            code = 1
        finally:
            os._exit(code)
    return pid


def _report(status: socket.socket, header: dict[str, Any]) -> None:
    """Tell the caller; a caller that already gave up is not an error."""
    with contextlib.suppress(OSError):
        send_frame(status, header)


def _reap(children: dict[int, socket.socket], *, block: bool) -> None:
    """Reap ended children and report how each ended on its STATUS socket."""
    while children:
        try:
            pid, code = os.waitpid(-1, 0 if block else os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return
        status = children.pop(pid, None)
        if status is None:
            continue
        if os.WIFSIGNALED(code):
            _report(status, {"signal": os.WTERMSIG(code)})
        else:
            _report(status, {"exit": os.WEXITSTATUS(code)})
        status.close()


def main(argv: list[str]) -> int:
    control = socket.socket(fileno=int(argv[1]))
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    wake, wake_in = os.pipe()
    os.set_blocking(wake, False)
    os.set_blocking(wake_in, False)
    signal.set_wakeup_fd(wake_in)
    signal.signal(signal.SIGCHLD, lambda _signum, _frame: None)
    children: dict[int, socket.socket] = {}
    send_frame(control, {"status": "ready"})
    try:
        while True:
            readable = select.select([control, wake], [], [])[0]
            if wake in readable:
                with contextlib.suppress(BlockingIOError):
                    while os.read(wake, 4096):
                        pass
            _reap(children, block=False)
            if control not in readable:
                continue
            message, fds, _flags, _address = socket.recv_fds(control, 16, 2)
            if not message:
                return 0  # the service closed us (or died)
            if len(fds) != 2:
                for fd in fds:
                    os.close(fd)
                continue
            data, status = (socket.socket(fileno=fd) for fd in fds)
            pid = _fork(control, wake, data, status)
            data.close()
            children[pid] = status
            _report(status, {"pid": pid})
    finally:
        for pid in list(children):
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        _reap(children, block=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

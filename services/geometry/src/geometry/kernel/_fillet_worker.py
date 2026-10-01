"""The warm blend server: forks a fresh child per fillet/chamfer (see
:mod:`geometry.kernel.fillet_isolation`, which starts and talks to it).

Run as ``python -m geometry.kernel._fillet_worker <request fd> <reply fd>``.
It imports the kernel ONCE, says ``ready``, then for each request frame forks a
child that runs the blend under ``RLIMIT_CPU`` and writes the reply frame. The
server stays single-threaded (so forking it is safe), waits for the child with a
wall-clock deadline, and answers ``crashed`` (killed by a signal) or ``timeout``
(``SIGXCPU`` / the deadline) when the child could not answer itself. It exits
when its request pipe closes, i.e. when the service process goes away.

The pipes are dedicated descriptors, not stdout: OCCT prints to stdout.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportAttributeAccessIssue=false

import math
import os
import signal
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
    read_frame,
    read_shapes,
    write_all,
    write_shapes,
)
from geometry.kernel.naming import OpHistory

_OPS = {"fillet": _fillet, "chamfer": _chamfer}


def _blend(header: dict[str, Any], data: bytes) -> bytes:
    """The reply frame for one request (runs in the forked child)."""
    try:
        parts = read_shapes(data)
        body = (Solid if header["kind"] == "Solid" else Compound)(parts[0])
        edges = [Edge(TopoDS.Edge_s(shape)) for shape in parts[1:]]
        history = OpHistory() if header["history"] else None
        solids = _OPS[header["op"]](body, edges, float(header["size"]), history)
    except Exception as exc:  # OCCT failure modes are not a stable taxonomy
        return encode_frame({"status": "failed", "error": type(exc).__name__}, b"")
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


def _child(header: dict[str, Any], data: bytes, out: int) -> None:
    import resource

    soft = max(1, math.ceil(float(header["cpu"])))
    resource.setrlimit(resource.RLIMIT_CPU, (soft, soft + 1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    write_all(out, _blend(header, data))


def _serve_one(header: dict[str, Any], data: bytes) -> bytes:
    read_end, write_end = os.pipe()
    pid = os.fork()
    if pid == 0:  # the child: blend, answer, and leave without cleanup
        code = 0
        try:
            os.close(read_end)
            _child(header, data, write_end)
        except BaseException:
            code = 1
        finally:
            os._exit(code)
    os.close(write_end)
    reply: tuple[dict[str, Any], bytes] | None = None
    timed_out = False
    try:
        reply = read_frame(read_end, time.monotonic() + float(header["wall"]))
    except TimeoutError:
        timed_out = True
        os.kill(pid, signal.SIGKILL)
    finally:
        os.close(read_end)
    _pid, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        sig = os.WTERMSIG(status)
        killed = sig == signal.SIGKILL and reply is None  # RLIMIT_CPU's hard limit
        if timed_out or killed or sig == signal.SIGXCPU:
            return encode_frame({"status": "timeout"}, b"")
        if reply is None:
            return encode_frame({"status": "crashed", "signal": sig}, b"")
    if reply is None:
        return encode_frame({"status": "crashed", "signal": 0}, b"")
    return encode_frame(*reply)


def main(argv: list[str]) -> int:
    requests, replies = int(argv[1]), int(argv[2])
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    write_all(replies, encode_frame({"status": "ready"}, b""))
    while True:
        request = read_frame(requests, None)
        if request is None:
            return 0
        write_all(replies, _serve_one(*request))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""BLEND-ROUTE-VERTEX-NEIGHBOUR: an analytic-routed blend that segfaults.

:func:`~geometry.kernel.fillet_isolation.needs_isolation` kept a blend
in-process (until every blend was isolated) when the picked edges are
lines/circles/ellipses and the faces on them are
planes/cylinders/cones/spheres. This body is ALL PLANES: a 40x30x20 box with a
triangular boss (67.5 mm^2, 10 mm tall) extruded from its top face, one
footprint corner snapped ON the box's corner vertex (0,0,20). The top face's
loop then passes through that vertex twice (six edges meet there). An R1
fillet or a 1 mm chamfer of the box's vertical edge x=0,y=0, which ends at
that vertex, SIGSEGVs inside ``ChFi3d`` (OCCT 7.9.3) at every size probed
(0.3-8 mm), in-process, so the geometry worker dies.

Surface type does not predict it: a slanted planar boss (no collinear edge, a
one-edge contour) crashes too, as does a twisted ruled-loft (B-spline) boss at
the same corner; a boss corner in mid-edge does not. Picking the vertex's
other box edges with it avoids the crash.

Every blend now runs in the blend server, so each case runs the blend through
the service path in a subprocess, which must survive with a typed error (or a
built body). The raw call is pinned too: while OCCT still crashes there, the
isolation is what holds.
"""

import signal
import subprocess
import sys
import textwrap

import pytest

_CASE = """
import sys
from build123d import Plane, Polyline, Solid, extrude, make_face
from geometry.kernel.chamfer import ChamferError, chamfer_body
from geometry.kernel.fillet import FilletError, fillet_body
from geometry.kernel.fillet_isolation import needs_isolation

footprint = Plane.XY.offset(20) * Polyline((0, 0), (12, 3), (3, 12), close=True)
boss = extrude(make_face(footprint), 10)
(body,) = Solid.make_box(40, 30, 20).fuse(boss).clean().solids()
# 40*30*20 + 10 * (12*12 - 3*3) / 2
assert abs(body.volume - 24675.0) < 1e-6, body.volume
assert {f.geom_type.name for f in body.faces()} == {"PLANE"}
(edge,) = [
    e for e in body.edges()
    if e.geom_type.name == "LINE"
    and abs(e.center().X) < 1e-9 and abs(e.center().Y) < 1e-9 and e.center().Z < 20
]
op = sys.argv[1]
blend = fillet_body if op == "fillet" else chamfer_body
try:
    out = blend(body, [edge], 1.0)
    print("built", out.volume)
except (FilletError, ChamferError) as exc:
    print("typed error:", exc)
"""


@pytest.mark.parametrize("op", ["fillet", "chamfer"])
def test_a_blend_ending_at_a_pinched_corner_does_not_kill_the_process(op: str) -> None:
    done = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_CASE), op],
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert done.returncode != -signal.SIGSEGV, "the blend segfaulted in-process"
    assert done.returncode == 0, done.stderr[-2000:]
    assert b"typed error:" in done.stdout or b"built" in done.stdout


@pytest.mark.parametrize("op", ["fillet", "chamfer"])
def test_the_crash_is_still_in_occt(op: str) -> None:
    """The raw blend still dies; when OCCT fixes it this fails, and the
    always-isolate rule can be reconsidered."""
    raw = _CASE.replace(
        "    out = blend(body, [edge], 1.0)",
        "    out = (body.fillet(1.0, [edge]) if op == 'fillet'"
        " else body.chamfer(1.0, None, [edge]))",
    )
    done = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(raw), op],
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == -signal.SIGSEGV, done.stderr[-2000:]

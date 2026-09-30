"""A shell is a pure function of its input (GEOMETRY-QA 2026-09-25 R2-F1).

OCCT's Arc-join hollow orders the offset faces it intersects by a hash of the
input's TShape ADDRESSES (``BRepOffset_MakeOffset::BuildOffsetByArc`` walks a
hash map). Faces adjacent to an opened face leave that map first, so an open
shell of a prism came out the same every time, but a SEALED hollow (the Shell
editor's default) did not: the cavity's faces came back in a different order on
every build, and on a spline wall its fitted edges and volume moved too.
:mod:`geometry.kernel.shell` now also builds a sealed hollow of an analytic
body with no concave edge by the Intersection join, and ships that byte-stable
build when it matches Arc's. Every other address-ordered hollow gets its faces in
a canonical order.

Pinned here, each on bodies rebuilt from scratch (fresh TShapes, so fresh
addresses) the way every product rebuild does:

* a sealed hollow of an analytic body with no concave edge is byte-identical
  (BREP) across rebuilds, and across a fresh interpreter (a worker restart): a
  box, a cylinder, a chamfered box, a box with filleted vertical edges;
* what ships is Arc's hollow: the same surfaces, volume and area, including a
  fillet smaller than the wall (both joins collapse it to a sharp cavity
  corner);
* the Intersection join is never trusted alone. A plate bored nearly through
  its width, whose cavity must split into two pockets, gets one pocket from it
  (20% to 65% heavy) while Arc raises; the shell raises, or reads the true
  volume. Where it quietly returns the un-hollowed body (fillet r == wall), Arc
  decides the outcome too;
* a spline wall takes Arc. The Intersection route read up to 1.84e-2 mm^3 off
  its true volume;
* a body WITH a concave edge keeps Arc's rounded cavity corner (its tube face),
  so the route does not change what a shell means;
* where Arc's result ships (a concave edge; fillets the Intersection join
  refuses; a spline wall; an open shell that leaves two or more faces off every
  opened face), the face ORDER is fixed across rebuilds, including faces that
  tie on centroid and area. The bytes are not (the module docstring measures
  that residual).

The sealed box is also a golden (``shell-sealed-box-40x25x10-t2``), so the
harness pins its GLB bytes in process and across an interpreter restart.
"""

# The OCP wheel ships no type stubs; scoped to this file as in the kernel.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportAttributeAccessIssue=false
# pyright: reportUnknownArgumentType=false, reportPrivateUsage=false
# pyright: reportUnknownParameterType=false

import hashlib
import importlib.util
import math
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from build123d import (
    Axis,
    Box,
    Cylinder,
    Edge,
    Face,
    Location,
    Solid,
    Vector,
    Wire,
    chamfer,
    extrude,
    fillet,
)
from geometry.kernel.properties import volume_properties
from geometry.kernel.shell import ShellError, _face_key, shell_body
from geometry.kernel.types import BodyShape
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Face

#: Fresh builds per body. Before the fix every one of 4 differed (box, spline).
TESTS = Path(__file__).resolve().parent
BUILDS = 4

#: QA's case-2 fit (test_offset_surface_qa.CASE2_FIT): a spline prism wall.
SPLINE_FIT = (
    (40.0, 10.0),
    (32.0, 16.0),
    (24.0, 11.0),
    (16.0, 17.0),
    (8.0, 12.0),
    (0.0, 15.0),
)


def _box() -> Solid:
    return Box(40, 25, 10).solids()[0]


def _spline_prism() -> Solid:
    fit = SPLINE_FIT
    wire = Wire(
        [
            Edge.make_line((0, 0, 0), (40, 0, 0)),
            Edge.make_line((40, 0, 0), (40, fit[0][1], 0)),
            Edge.make_spline([Vector(x, y, 0) for x, y in fit]),
            Edge.make_line((0, fit[-1][1], 0), (0, 0, 0)),
        ]
    )
    return extrude(Face(wire), 20.0).solids()[0]


def _cylinder() -> Solid:
    return Cylinder(10, 20).solids()[0]


def _chamfered_box() -> Solid:
    return chamfer(_box().edges(), 1.5).solids()[0]


def _vertical_fillets(radius: float) -> Callable[[], Solid]:
    """An enclosure blank: the four vertical edges filleted (tangent edges, no
    concave one), which the Intersection join accepts."""

    def make() -> Solid:
        return fillet(_box().edges().filter_by(Axis.Z), radius).solids()[0]

    return make


def _l_block() -> Solid:
    """An L: one concave edge, where Arc rounds the cavity with a tube."""
    arm = Box(20, 40, 10).solids()[0].moved(Location((-10, 10, 0)))
    return _box().fuse(arm).clean().solids()[0]


def _filleted_box() -> Solid:
    """Tangent fillets along the bottom: the Intersection join refuses this."""
    box = _box()
    return fillet(box.edges().group_by(Axis.Z)[0], 3.0).solids()[0]


def _top(body: Solid) -> list[Face]:
    return [max(body.faces(), key=lambda f: f.center().Z)]


def _sealed_faces(_body: Solid) -> list[Face]:
    return []


def _sealed(make: Callable[[], Solid]) -> BodyShape:
    return shell_body(make(), [], 2.0)


def _brep(shape: BodyShape, path: Path) -> bytes:
    assert BRepTools.Write_s(shape.wrapped, str(path))
    return path.read_bytes()


def _face_order(shape: BodyShape) -> list[tuple[float, ...]]:
    return [tuple(round(c, 6) for c in f.center()) for f in shape.faces()]


def _surface_types(shape: BodyShape) -> list[str]:
    return sorted(BRepAdaptor_Surface(f.wrapped).GetType().name for f in shape.faces())


def _fingerprint(make: Callable[[], Solid], path: Path) -> str:
    """BREP digest, reported mass properties and topology of a sealed hollow."""
    body = _sealed(make)
    reading = volume_properties(body)
    counts = (len(body.faces()), len(body.edges()), len(body.shells()))
    digest = hashlib.sha256(_brep(body, path)).hexdigest()
    return f"{digest} {reading.volume!r} {reading.centroid!r} {body.area!r} {counts}"


#: Bodies the Intersection route takes, by name (the restart probe looks them
#: up in this module).
NO_CONCAVE_EDGE = {
    "box": _box,
    "cylinder": _cylinder,
    "chamfered-box": _chamfered_box,
    "vertical-fillets-r4": _vertical_fillets(4.0),
}


@pytest.mark.parametrize("name", list(NO_CONCAVE_EDGE))
def test_a_sealed_hollow_without_concave_edges_rebuilds_byte_identically(
    name: str, tmp_path: Path
) -> None:
    breps = {
        _brep(_sealed(NO_CONCAVE_EDGE[name]), tmp_path / f"{i}.brep")
        for i in range(BUILDS)
    }
    assert len(breps) == 1, f"{len(breps)} distinct BREPs in {BUILDS} rebuilds"


#: Rebuilds one sealed hollow in a pristine interpreter (worker-restart
#: emulation, RESEARCH §9) and prints its fingerprint.
_RESTART_PROBE = """\
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("shell_probe", {module!r})
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
print(mod._fingerprint(mod.NO_CONCAVE_EDGE[{name!r}], Path({path!r})))
"""


@pytest.mark.parametrize("name", ["chamfered-box", "vertical-fillets-r4"])
def test_a_sealed_hollow_is_identical_across_a_worker_restart(
    name: str, tmp_path: Path
) -> None:
    """Addresses differ in a fresh process, which is what broke the Arc route.
    The box is the golden, whose runner gates this for GLB and metadata."""
    here = _fingerprint(NO_CONCAVE_EDGE[name], tmp_path / "here.brep")
    probe = _RESTART_PROBE.format(
        module=__file__, name=name, path=str(tmp_path / "there.brep")
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, f"restart probe failed:\n{result.stderr}"
    assert result.stdout.strip() == here


@pytest.mark.parametrize(
    "make",
    [_cylinder, _chamfered_box, _vertical_fillets(4.0), _vertical_fillets(1.0)],
    ids=["cylinder", "chamfered-box", "vertical-fillets-r4", "vertical-fillets-r1"],
)
def test_the_intersection_route_builds_the_arc_hollow(
    make: Callable[[], Solid],
) -> None:
    """Same surfaces and volume as OCCT's Arc join. At r1 < t the fillets
    collapse to a sharp cavity corner under both joins."""
    body = make()
    arc = body.hollow([], -2.0).solids()[0]
    ours = shell_body(body, [], 2.0)
    assert _surface_types(ours) == _surface_types(arc)
    assert ours.volume == pytest.approx(arc.volume, abs=1e-9)
    assert ours.area == pytest.approx(arc.area, abs=1e-9)


def test_a_quietly_unhollowed_intersection_result_falls_back_to_arc() -> None:
    """Every edge filleted at r == t: the Intersection join returns the body
    un-hollowed, and Arc raises. The user gets Arc's outcome, not a new
    'thickness too large' that only the route produced."""
    body = fillet(_box().edges(), 2.0).solids()[0]
    with pytest.raises(ShellError):
        shell_body(body, [], 2.0)


def test_the_sealed_box_is_its_analytic_hollow() -> None:
    body = _sealed(_box)
    assert body.volume == pytest.approx(10000.0 - 36 * 21 * 6, abs=1e-9)
    assert (len(body.faces()), len(body.edges()), len(body.shells())) == (12, 24, 2)


def test_the_sealed_spline_prism_has_the_arc_faces() -> None:
    """6 outer faces, 6 cavity faces, the cavity's spline wall an offset of the
    outer one."""
    body = _sealed(_spline_prism)
    assert len(body.shells()) == 2
    assert _surface_types(body) == sorted(
        ["GeomAbs_Plane"] * 10 + ["GeomAbs_SurfaceOfExtrusion", "GeomAbs_OffsetSurface"]
    )


def test_a_concave_edge_keeps_the_rounded_cavity_corner() -> None:
    """Arc puts a tube (a cylinder face) on the L's concave edge; the
    Intersection join would leave a sharp corner. The route must not change
    what a shell means, so the L still gets its tube."""
    body = _sealed(_l_block)
    assert "GeomAbs_Cylinder" in _surface_types(body)


@pytest.mark.parametrize(
    ("make", "opened"),
    [
        (_l_block, _sealed_faces),
        (_filleted_box, _sealed_faces),
        (_filleted_box, _top),
        (_spline_prism, _sealed_faces),
    ],
    ids=["L-sealed", "filleted-sealed", "filleted-open-top", "spline-sealed"],
)
def test_an_arc_hollow_keeps_its_face_order(
    make: Callable[[], Solid], opened: Callable[[Solid], list[Face]]
) -> None:
    orders = []
    for _ in range(BUILDS):
        body = make()
        orders.append(_face_order(shell_body(body, opened(body), 2.0)))
    assert all(order == orders[0] for order in orders)


def _plate(radius: float) -> Solid:
    """A 40 x 20 x 10 plate with a centred through-hole: no concave edge."""
    return (Box(40, 20, 10) - Cylinder(radius, 10)).solids()[0]


def _plate_hollow_truth(radius: float, wall: float) -> float:
    """The sealed hollow's volume, by hand. The cavity is the prism over the
    inner rectangle ``(40 - 2t) x (20 - 2t)`` minus the disc of radius
    ``R = r + t``, ``10 - 2t`` tall. When ``R`` exceeds the inner half-width
    ``h = 10 - t`` the disc cuts the rectangle in two, and it removes the strip
    ``|y| <= h`` of the disc: ``2 (h sqrt(R^2 - h^2) + R^2 asin(h / R))``."""
    outer, half = radius + wall, 10.0 - wall
    if outer <= half:
        disc = math.pi * outer**2
    else:
        disc = 2 * (
            half * math.sqrt(outer**2 - half**2) + outer**2 * math.asin(half / outer)
        )
    cavity = ((40 - 2 * wall) * (20 - 2 * wall) - disc) * (10 - 2 * wall)
    return 8000.0 - math.pi * radius**2 * 10 - cavity


def test_the_plate_truth_matches_the_reported_volumes() -> None:
    """The hand formula, checked against the numbers the review derived:
    r 8.5 t 1 -> 2493.813, r 8.5 t 2 -> 4073.117, r 7 t 2 -> 4464.694."""
    assert _plate_hollow_truth(8.5, 1.0) == pytest.approx(2493.813, abs=1e-3)
    assert _plate_hollow_truth(8.5, 2.0) == pytest.approx(4073.117, abs=1e-3)
    assert _plate_hollow_truth(7.0, 2.0) == pytest.approx(4464.694, abs=1e-3)


@pytest.mark.parametrize(
    ("radius", "wall"),
    [(8.5, 1.0), (8.5, 2.0), (7.0, 2.0)],
    ids=["r8.5-t1", "r8.5-t2", "r7-t2"],
)
def test_a_split_cavity_is_never_shipped_as_one_pocket(
    radius: float, wall: float
) -> None:
    """The cavity must split in two either side of the bore. At 1fda3e0 the
    Intersection join's one-pocket solid shipped: 4112.006, 4901.658 and
    5462.657 mm^3. Arc raises on all three today; if a join ever builds them,
    it must read the true volume."""
    try:
        body = shell_body(_plate(radius), [], wall)
    except ShellError:
        return
    assert volume_properties(body).volume == pytest.approx(
        _plate_hollow_truth(radius, wall), abs=1e-6
    )


@pytest.mark.parametrize(
    ("radius", "wall"), [(3.0, 1.0), (5.0, 2.0)], ids=["r3-t1", "r5-t2"]
)
def test_a_bored_plate_with_one_cavity_reads_its_true_volume(
    radius: float, wall: float, tmp_path: Path
) -> None:
    """The control: the cavity stays whole, both joins agree, and the
    Intersection build ships byte-identically."""
    body = shell_body(_plate(radius), [], wall)
    assert volume_properties(body).volume == pytest.approx(
        _plate_hollow_truth(radius, wall), abs=1e-9
    )
    breps = {
        _brep(shell_body(_plate(radius), [], wall), tmp_path / f"{i}.brep")
        for i in range(BUILDS)
    }
    assert len(breps) == 1


def _qa() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "offset_qa_round1_shell", TESTS / "test_offset_surface_qa.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("wall", [0.5, 1.0], ids=["t0.5", "t1"])
def test_a_sealed_spline_wall_reads_its_true_volume(wall: float) -> None:
    """At 1fda3e0 the Intersection route read -1.84e-2 (t 0.5) and +5.0e-4
    (t 1) mm^3 off the truth; Arc reads -9.3e-7 and -1.1e-5. The bound is 2x
    the sealed Arc route's measured worst on this prism (4.4e-5 at t 2 through
    the pipeline, 5.5e-5 raw), so only a wrong route breaks it."""
    # The open-shell truth's profile areas: the sealed cavity is the inner
    # parallel region, 20 - 2t tall.
    profile = _qa()._polygon_truth(40.0, 20.0, wall, SPLINE_FIT)
    truth = profile.area * 20.0 - profile.area_in * (20.0 - 2 * wall)
    body = shell_body(_spline_prism(), [], wall)
    assert volume_properties(body).volume == pytest.approx(truth, abs=1e-4)


def _planar_face(width: float, depth: float) -> TopoDS_Face:
    return Face.make_rect(width, depth).wrapped


def test_faces_tied_on_centroid_and_area_still_sort_one_way() -> None:
    """A 2 x 2 and a 1 x 4 rectangle, both centred on the origin: the same
    centroid and area, so without a tiebreak their order was OCCT's."""
    square, strip = _planar_face(2.0, 2.0), _planar_face(1.0, 4.0)
    assert _face_key(square)[:4] == _face_key(strip)[:4]
    assert _face_key(square) != _face_key(strip)
    forward = sorted([square, strip], key=_face_key)
    backward = sorted([strip, square], key=_face_key)
    assert [f.IsSame(g) for f, g in zip(forward, backward, strict=True)] == [True, True]

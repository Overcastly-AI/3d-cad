"""The fillet's re-seam retry (:mod:`geometry.kernel.reseam`).

A cylinder's seam on (or beside) an edge being filleted makes OCCT's blend
fail. The retry turns the seam clear of the edges on the same solid; it must
give exactly the body a seam elsewhere would have given, and nothing else.
"""

import math

from build123d import (
    Axis,
    Cylinder,
    Edge,
    GeomType,
    Plane,
    Polyline,
    Pos,
    Solid,
    loft,
    make_face,
)
from geometry.kernel.fillet import FilletError, fillet_body
from geometry.kernel.reseam import reseam_near

HUB_R = 22.0


def _hub_with_blade(seam_deg: float) -> tuple[Solid, list[Edge]]:
    """The QA blade's root on a Ø44 hub whose seam is turned *seam_deg*: at 0
    the seam crosses the blade's r3 root curve."""
    hub = (Pos(0, 0, 10) * Cylinder(HUB_R, 20)).rotate(Axis.Z, seam_deg)
    root = [(18.0, -1.0), (50.0, -8.0), (50.0, -6.0), (18.0, 1.0)]
    tip = [(18.0, -1.0), (50.0, -14.0), (50.0, -12.0), (18.0, 1.0)]
    blade = loft(
        [
            make_face(Plane.XY.offset(2) * Polyline(*root, close=True)),
            make_face(Plane.XY.offset(18) * Polyline(*tip, close=True)),
        ],
        ruled=True,
    )
    body = hub.fuse(blade).clean()  # pyright: ignore[reportUnknownMemberType]
    (solid,) = body.solids()
    roots = [
        e
        for e in solid.edges()
        if e.geom_type not in (GeomType.LINE, GeomType.CIRCLE)
        and all(
            abs(math.hypot((e @ t).X, (e @ t).Y) - HUB_R) < 1e-6 for t in (0, 0.5, 1)
        )
    ]
    return solid, roots


def test_a_seam_on_the_root_curve_defeats_the_plain_fillet() -> None:
    """The defect the retry exists for, reproduced without it."""
    solid, roots = _hub_with_blade(0.0)
    assert len(roots) == 3  # r1, and r3 cut in two by the seam
    try:
        solid.fillet(1.0, roots)
    except ValueError:
        return
    raise AssertionError("OCCT filleted across the seam; the retry may be moot")


def test_the_retry_gives_the_body_a_seam_elsewhere_gives() -> None:
    crossing, roots = _hub_with_blade(0.0)
    clear, clear_roots = _hub_with_blade(180.0)
    assert len(clear_roots) == 2
    rescued = fillet_body(crossing, roots, 1.0)
    oracle = fillet_body(clear, clear_roots, 1.0)
    assert rescued.is_valid
    assert abs(rescued.volume - oracle.volume) < 1e-6
    assert len(rescued.faces()) == len(oracle.faces())


def test_the_re_seamed_solid_is_the_same_solid() -> None:
    solid, roots = _hub_with_blade(0.0)
    moved = reseam_near(solid, roots)
    assert moved is not None
    body, edges = moved
    assert body.is_valid
    assert abs(body.volume - solid.volume) <= 1e-9 * solid.volume
    assert len(body.faces()) == len(solid.faces())
    assert len(edges) == len(roots)


def test_a_fillet_that_cannot_build_still_fails_typed() -> None:
    """The retry never turns a real refusal into a body: a radius too large
    for the blade is still ``FilletError``."""
    solid, roots = _hub_with_blade(0.0)
    try:
        fillet_body(solid, roots, 40.0)
    except FilletError:
        return
    raise AssertionError("an R40 root fillet on a 2 mm blade built")

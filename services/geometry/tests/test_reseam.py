"""The fillet's re-seam retry (:mod:`geometry.kernel.reseam`).

A cylinder's seam on (or beside) an edge being filleted makes OCCT's blend
fail. The retry turns the seam clear of the edges on the same solid; it must
give exactly the body a seam elsewhere would have given, and nothing else.
"""

import contextlib
import math
from typing import Any

from build123d import (
    Axis,
    Box,
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
from geometry.kernel.fillet_guard import TOLERANCE_FLOOR_MM, max_tolerance
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


# --- review of 8dedc83: a failed fillet must not damage anything ---------------


#: How far two fits of the same R1 blend set may differ (mm^3).
_BLEND_FIT_MM3 = 1e-4


def _blade_zero_roots(solid: Solid) -> list[Edge]:
    """Root edges on the Ø44 hub whose midpoint lies within 40 deg of +X."""
    out: list[Edge] = []
    for e in solid.edges():
        if e.geom_type in (GeomType.LINE, GeomType.CIRCLE):
            continue
        if not all(
            abs(math.hypot((e @ t).X, (e @ t).Y) - HUB_R) < 1e-6 for t in (0, 0.5, 1)
        ):
            continue
        mid = e @ 0.5
        if abs(math.degrees(math.atan2(mid.Y, mid.X))) < 40:
            out.append(e)
    return out


def _cone_with_blade(seam_deg: float) -> tuple[Solid, list[Edge]]:
    """The QA blade on a cone hub (r 24 -> 20 over z 0..20) whose seam is
    turned *seam_deg*: at 0 OCCT's plain fillet fails AND, before this fix,
    left a vertex of the input at a 74 mm tolerance."""
    hub = Solid.make_cone(24, 20, 20).rotate(Axis.Z, seam_deg)
    body = hub.fuse(_blade()).clean()  # pyright: ignore[reportUnknownMemberType]
    (solid,) = body.solids()
    roots = [
        e
        for e in solid.edges()
        if e.geom_type not in (GeomType.LINE, GeomType.CIRCLE)
        and all(
            abs(math.hypot((e @ t).X, (e @ t).Y) - (24 - 4 * (e @ t).Z / 20)) < 1e-5
            for t in (0, 0.5, 1)
        )
    ]
    return solid, roots


def _blade() -> Any:
    root = [(18.0, -1.0), (50.0, -8.0), (50.0, -6.0), (18.0, 1.0)]
    tip = [(18.0, -1.0), (50.0, -14.0), (50.0, -12.0), (18.0, 1.0)]
    return loft(
        [
            make_face(Plane.XY.offset(2) * Polyline(*root, close=True)),
            make_face(Plane.XY.offset(18) * Polyline(*tip, close=True)),
        ],
        ruled=True,
    )


def test_the_cone_hub_rescue_is_tight_and_right_downstream() -> None:
    """The reviewer's case: the rescued body is no looser than a blend needs,
    and a later cut through the blade removes what it removes from the body a
    seam elsewhere gives (31367.58, where the damaged one gave 30998.1)."""
    crossing, roots = _cone_with_blade(0.0)
    clear, clear_roots = _cone_with_blade(180.0)
    rescued = fillet_body(crossing, roots, 1.0)
    oracle = fillet_body(clear, clear_roots, 1.0)
    assert max_tolerance(rescued) <= TOLERANCE_FLOOR_MM
    # OCCT fits a blend afresh for each seam placement: the same blend lands
    # within ~2e-5 mm^3 (measured at 0/45/90/180 deg); a wrong body is off by
    # hundreds.
    assert abs(rescued.volume - oracle.volume) < _BLEND_FIT_MM3
    pocket = Pos(30, -3, 10) * Box(4, 4, 4)
    cut = rescued.cut(pocket)  # pyright: ignore[reportUnknownMemberType]
    reference = oracle.cut(pocket)  # pyright: ignore[reportUnknownMemberType]
    assert abs(cut.volume - reference.volume) < _BLEND_FIT_MM3


def test_a_fillet_never_touches_its_input() -> None:
    """OCCT fillets in place, and a failed attempt can loosen the input's
    vertices to tens of mm. The input must leave fillet_body exactly as it
    came: same tolerances, and a later cut gives the same volume as on a fresh
    build."""
    crossing, roots = _cone_with_blade(0.0)
    before = max_tolerance(crossing)
    fillet_body(crossing, roots, 1.0)
    assert max_tolerance(crossing) == before
    with contextlib.suppress(FilletError):
        fillet_body(crossing, roots, 40.0)
    assert max_tolerance(crossing) == before
    fresh, _roots = _cone_with_blade(0.0)
    hole = Pos(0, 0, 10) * Cylinder(3, 40)
    assert crossing.cut(hole).volume == fresh.cut(hole).volume  # pyright: ignore[reportUnknownMemberType]


def _two_blades(hub: Any) -> Any:
    """*hub* with blades at 0 and 180 deg, fused one at a time (the order the
    defect was measured in)."""
    body = hub
    for angle in (0.0, 180.0):
        body = body.fuse(_blade().rotate(Axis.Z, angle))  # pyright: ignore[reportUnknownMemberType]
    return body.clean()


def test_a_valid_but_wrong_plain_fillet_is_not_accepted() -> None:
    """Two blades at 0 and 180 deg on a cylinder hub, seam at 0: OCCT's plain
    R1 root fillet of blade 0 returns a BRepCheck-valid solid that has lost the
    top cap (24 746 mm^3). The locality check rejects it, and the re-seam retry
    gives the body a seam elsewhere gives (~32 212)."""
    hub = Pos(0, 0, 10) * Cylinder(HUB_R, 20)
    body = _two_blades(hub)  # pyright: ignore[reportUnknownMemberType]
    (solid,) = body.solids()
    roots = _blade_zero_roots(solid)
    plain = solid.fillet(1.0, roots)
    assert plain.volume < 25_000  # the defect, still in OCCT
    fresh_solid = _two_blades(hub)  # pyright: ignore[reportUnknownMemberType]
    (fresh,) = fresh_solid.solids()
    fresh_roots = _blade_zero_roots(fresh)
    rescued = fillet_body(fresh, fresh_roots, 1.0)
    turned = _two_blades(hub.rotate(Axis.Z, 90))  # pyright: ignore[reportUnknownMemberType]
    (clear,) = turned.solids()
    clear_roots = _blade_zero_roots(clear)
    oracle = clear.fillet(1.0, clear_roots)
    assert abs(rescued.volume - oracle.volume) < _BLEND_FIT_MM3

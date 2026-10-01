"""The fillet's re-seam retry (:mod:`geometry.kernel.reseam`).

A cylinder's seam on (or beside) an edge being filleted makes OCCT's blend
fail. The retry turns the seam clear of the edges on the same solid; it must
give exactly the body a seam elsewhere would have given, and nothing else.
"""

import contextlib
import math
import time
from typing import Any

import pytest
from build123d import (
    Axis,
    Box,
    Circle,
    Compound,
    Cylinder,
    Edge,
    GeomType,
    Plane,
    Polyline,
    Pos,
    Rectangle,
    Solid,
    loft,
    make_face,
)
from geometry.kernel.chamfer import ChamferError, chamfer_body
from geometry.kernel.fillet import (  # pyright: ignore[reportPrivateUsage]
    FilletError,
    _fillet,  # pyright: ignore[reportPrivateUsage]
    fillet_body,
)
from geometry.kernel.fillet_guard import (
    TOLERANCE_FLOOR_MM,
    fillet_problem,
    max_tolerance,
)
from geometry.kernel.fillet_isolation import working_copy as _working_copy
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


def test_a_chamfer_never_touches_its_input() -> None:
    """OCCT chamfers in place too (the same ChFi3d builder): the failed R1
    chamfer of the cone-hub blade root left an input vertex at 71.6 mm, and a
    successful one loosened it. The input must leave chamfer_body as it came."""
    crossing, roots = _cone_with_blade(0.0)
    before = max_tolerance(crossing)
    with pytest.raises(ChamferError):
        chamfer_body(crossing, roots, 1.0)
    assert max_tolerance(crossing) == before
    fresh, _roots = _cone_with_blade(0.0)
    hole = Pos(0, 0, 10) * Cylinder(3, 40)
    assert crossing.cut(hole).volume == fresh.cut(hole).volume  # pyright: ignore[reportUnknownMemberType]
    clear, clear_roots = _cone_with_blade(180.0)
    tight = max_tolerance(clear)
    chamfered = chamfer_body(clear, clear_roots, 1.0)
    assert max_tolerance(clear) == tight
    assert max_tolerance(chamfered) <= TOLERANCE_FLOOR_MM
    assert chamfered.volume == pytest.approx(31407.29, abs=0.01)


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


# --- re-review of 95a38e3: cost, false refusals, sample spread ------------------


def _lofted_cut_rim() -> tuple[Solid, list[Edge]]:
    """A 60x60x20 box minus a loft from a 30x20 rectangle at the top to a Ø16
    circle below: OCCT fits its rim blends at 3-5e-3 mm, correctly."""
    box = Box(60, 60, 20)
    cut = loft(
        [
            Pos(0, 0, 10) * Rectangle(30, 20).face(),
            Plane.XY.offset(-5) * Circle(8).face(),
        ]
    )
    (solid,) = (box - cut).solids()  # pyright: ignore[reportOperatorIssue]
    rim = [
        e
        for e in solid.edges().group_by(Axis.Z)[-1]
        if abs((e @ 0.5).X) < 29 and abs((e @ 0.5).Y) < 29
    ]
    return solid, rim


@pytest.mark.parametrize("radius", [1.0, 1.5])
def test_a_correct_fillet_with_a_loose_blend_is_not_refused(radius: float) -> None:
    """The 1e-3 mm ceiling refused these (3e-3 and 5e-3 mm, volumes right)."""
    solid, rim = _lofted_cut_rim()
    assert len(rim) == 5
    filleted = fillet_body(solid, rim, radius)
    assert filleted.is_valid
    assert filleted.volume < solid.volume  # a rim round removes material


def _lid(slots: int) -> tuple[Solid, list[Edge]]:
    holes = [
        Pos(-110 + 8 * i, -70 + 10 * j, 0) * Box(4, 6, 10)
        for i in range(28)
        for j in range(15)
    ][:slots]
    (solid,) = (Box(240, 160, 6) - Compound(children=holes)).clean().solids()  # pyright: ignore[reportOperatorIssue]
    top = [
        e
        for e in solid.edges().group_by(Axis.Z)[-1]
        if abs(abs((e @ 0.5).X) - 120) < 1e-6 or abs(abs((e @ 0.5).Y) - 80) < 1e-6
    ]
    return solid, top


def test_the_guard_costs_a_fraction_of_the_fillet() -> None:
    """PERF TRIPWIRE. The first guard ray-cast the whole solid per sample:
    127 s at 906 faces against a 0.9 s fillet. It must stay linear and cheap:
    here (a 246-face slotted lid, R2 on its four outer edges) well under half
    of the OCCT fillet it checks (measured ~6 % at 906 faces)."""
    solid, top = _lid(60)
    assert len(solid.faces()) == 246
    work, work_edges = _working_copy(solid, top)
    start = time.perf_counter()
    solids = _fillet(work, work_edges, 2.0, None)
    blend = time.perf_counter() - start
    start = time.perf_counter()
    assert fillet_problem(work, work_edges, 2.0, solids, max_tolerance(solid)) is None
    guard = time.perf_counter() - start
    assert guard < 0.5 * blend + 0.05, (guard, blend)


@pytest.mark.parametrize("op", ["cut", "fuse"])
def test_a_wrong_body_far_from_the_fillet_is_caught_anywhere(op: str) -> None:
    """Material removed or added at the far corner of a face the fillet
    touched (the samples used to cluster in one strip and missed it)."""
    plate = Box(100, 100, 10)
    (solid,) = plate.solids()
    corner = [
        e
        for e in solid.edges()
        if e.geom_type == GeomType.LINE
        and abs((e @ 0.5).X + 50) < 1e-6
        and abs((e @ 0.5).Y + 50) < 1e-6
    ]
    work, work_edges = _working_copy(solid, corner)
    (good,) = _fillet(work, work_edges, 1.0, None)
    assert fillet_problem(work, work_edges, 1.0, [good], 1e-7) is None
    good_any: Any = good
    if op == "cut":
        wrong = good_any.cut(Pos(40, 40, 5) * Box(20, 20, 4))
    else:
        wrong = good_any.fuse(Pos(40, 40, 7) * Box(20, 20, 4))
    (bad,) = wrong.clean().solids()
    assert fillet_problem(work, work_edges, 1.0, [bad], 1e-7) is not None


def test_a_refusal_says_what_was_found() -> None:
    """The message names the defect, not a guessed radius."""
    hub = Pos(0, 0, 10) * Cylinder(HUB_R, 20)
    (fresh,) = _two_blades(hub).solids()
    roots = _blade_zero_roots(fresh)
    work, work_edges = _working_copy(fresh, roots)
    solids = _fillet(work, work_edges, 1.0, None)
    problem = fillet_problem(work, work_edges, 1.0, solids, max_tolerance(fresh))
    assert problem is not None
    assert "radius" not in problem

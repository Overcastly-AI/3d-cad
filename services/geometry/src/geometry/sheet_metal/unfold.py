"""The sheet-metal unfold (SPIKE 0) — folded body → :class:`FlatPattern`.

This is the pillar's genuine kernel risk (docs/design/sheet-metal.md §2): OCCT
ships no turnkey unfold, so we build it. SPIKE 0 proves the simplest real case
end-to-end — an **L-bracket** (a base flange + ONE edge flange folded 90°) —
before the feature schema is committed.

Algorithm (§6, scoped to a depth-1 bend star — every bend folds directly off
the fixed base flange, so no graph relaxation is needed, §4.3):

1. Resolve each bend region (:mod:`geometry.sheet_metal.resolve`): its inner
   cylindrical face (radius, axis) + the two flat flanges it connects, each
   flange's developed length measured to the bend **tangent line** (§9 #1).
2. Compute the **bend allowance** ``BA = angle_rad * (radius + K * thickness)``
   (§1) — the flat length that replaces the two setback segments a sharp-corner
   unfold would use (the neutral-axis math is precisely why the flat blank is
   dimensionally different from a naive projection).
3. Lay the developed flanges + BA strips out flat and emit the outline + tagged
   bend lines as a :class:`FlatPattern`.

**Spike scope:** SPIKE 0 targets the single-bend L-bracket, where the developed
blank is a rectangle and ``flat_length = leg1_dev + BA + leg2_dev`` is a single
scalar along the fold-perpendicular axis. A general depth-1 star with N ≥ 2
edge flanges develops into a 2D outline with N legs radiating from the base;
that layout is the feature slice's work — this spike proves the bend math + the
OCCT resolution the star reuses per-bend. :func:`unfold_l_bracket` raises if the
body is not a single-bend bracket, keeping the spike honest about its scope.
"""

import math

from geometry.kernel.types import BodyShape
from geometry.sheet_metal.flat_pattern import BendLine, FlatEdge2D, FlatPattern
from geometry.sheet_metal.resolve import (
    SheetMetalUnfoldError,
    resolve_bends,
)


class UnfoldScopeError(SheetMetalUnfoldError):
    """The body is outside SPIKE 0's single-bend L-bracket scope."""


def bend_allowance(
    angle_rad: float, radius_mm: float, k_factor: float, thickness_mm: float
) -> float:
    """The bend allowance ``BA = angle_rad * (radius + K * thickness)`` (§1).

    The neutral axis sits ``K * thickness`` from the INNER bend face (§9's pinned
    convention); ``BA`` is the developed length of the bent arc measured along
    that neutral surface. Four-term closed form, no numeric dependency (§7).
    """
    return angle_rad * (radius_mm + k_factor * thickness_mm)


def unfold_l_bracket(
    body: BodyShape, thickness_mm: float, k_factor: float
) -> FlatPattern:
    """Unfold a single-bend L-bracket into its :class:`FlatPattern` (SPIKE 0).

    Resolves the one bend geometrically (:func:`resolve_bends`), computes its
    bend allowance, and develops the base + edge flanges flat with the bend
    region replaced by a ``BA``-length strip. The output is byte-deterministic
    (§9 #4): every value flows from a deterministic OCCT measurement + the
    closed-form allowance.

    Raises:
        NoBendFoundError / BendFlankingFacesError: the body is not a folded sheet
            at *thickness_mm* (from :func:`resolve_bends`).
        UnfoldScopeError: the body has other than exactly one bend (SPIKE 0 is
            the L-bracket; multi-bend stars are the feature slice).
    """
    bends = resolve_bends(body, thickness_mm)
    if len(bends) != 1:
        raise UnfoldScopeError(
            f"SPIKE 0 unfolds a single-bend L-bracket; found {len(bends)} bends. "
            "Multi-bend depth-1 stars are the feature slice (§4.3)."
        )
    bend = bends[0]
    base, edge = bend.flanges  # base = longer developed leg (deterministic, §resolve)

    ba = bend_allowance(bend.angle_rad, bend.radius_mm, k_factor, thickness_mm)
    width = bend.bend_width_mm
    leg1 = base.developed_length_mm
    leg2 = edge.developed_length_mm

    flat_length = leg1 + ba + leg2
    # §9 golden #2: developed area conserves the neutral surface — flange flats
    # unchanged + the bend strip is BA * width. Equivalently flat_length * width
    # for this rectangular blank; written as the sum to mirror the invariant.
    flat_area = (leg1 * width) + (leg2 * width) + (ba * width)

    # Developed (u, v) frame: u along the fold-perpendicular axis, v the width.
    # Bend strip occupies u ∈ [leg1, leg1 + BA]; fold centerline at its midpoint.
    bend_u0 = leg1
    bend_u1 = leg1 + ba
    cu = leg1 + ba / 2.0  # fold centerline in the developed frame

    fl = flat_length
    outline: tuple[FlatEdge2D, ...] = (
        FlatEdge2D(kind="line", x1=0.0, y1=0.0, x2=fl, y2=0.0, role="body"),
        FlatEdge2D(kind="line", x1=fl, y1=0.0, x2=fl, y2=width, role="body"),
        FlatEdge2D(kind="line", x1=fl, y1=width, x2=0.0, y2=width, role="body"),
        FlatEdge2D(kind="line", x1=0.0, y1=width, x2=0.0, y2=0.0, role="body"),
        FlatEdge2D(kind="line", x1=cu, y1=0.0, x2=cu, y2=width, role="bend"),
    )

    bend_line = BendLine(
        bend_id="bend-1",
        angle_deg=math.degrees(bend.angle_rad),
        radius_mm=bend.radius_mm,
        k_factor=k_factor,
        allowance_mm=ba,
        width_mm=width,
        # SPIKE 0: a single 90° up-fold; up/down inference from face orientation
        # is a feature-slice detail (needs the base-flange provenance to know
        # which side is "material up"). Pinned "up" here, noted in the report.
        direction="up",
        flat_start_mm=bend_u0,
        flat_end_mm=bend_u1,
    )

    return FlatPattern(
        thickness_mm=thickness_mm,
        k_factor=k_factor,
        flat_length_mm=flat_length,
        flat_area_mm2=flat_area,
        bend_width_mm=width,
        outline=outline,
        bends=(bend_line,),
    )

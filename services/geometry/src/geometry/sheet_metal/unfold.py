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

The provenance star layout uses build123d ``Vector`` (the OCP wheel ships no type
stubs), opaque to pyright; the directives scope that relaxation to this file only,
and the typed DTOs at the boundary keep it honest.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false

import math
from dataclasses import dataclass
from typing import Literal

from build123d import Vector
from py_kit.schemas.features import CylindricalFaceSignature, PlanarFaceSignature

from geometry.kernel.faces import planar_signatures_match
from geometry.kernel.types import BodyShape
from geometry.sheet_metal.flat_pattern import BendLine, FlatEdge2D, FlatPattern
from geometry.sheet_metal.resolve import (
    FlangeFaceRecord,
    SheetMetalUnfoldError,
    resolve_bend_faces,
    resolve_bends,
    resolve_cylindrical_face,
)

#: Star-layout tolerance (documented, not ad-hoc — §9). Faces of an authored
#: sheet are axis-aligned, so residuals are ulp-scale. Cylinder-axis-specific
#: (not in faces.py); the planar-face match tolerances live once in
#: :mod:`geometry.kernel.faces` and are applied via :func:`planar_signatures_match`.
_PARALLEL_TOL = 1e-9  # 1 - |dot| between unit axis directions


class UnfoldScopeError(SheetMetalUnfoldError):
    """The body is outside SPIKE 0's single-bend L-bracket scope."""


class UnfoldStarError(SheetMetalUnfoldError):
    """The body is outside the v1 depth-1 PARALLEL bend-star unfold scope
    (docs/design/sheet-metal.md §4.3): a base flange + N edge flanges whose bends
    all share a parallel axis (the L-bracket and U-channel). Non-parallel stars
    (flanges off perpendicular edges) and depth >= 2 are deferred."""


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


# --- Provenance-driven unfold of an AUTHORED body (slice #3) ----------------------
#
# The spike's :func:`unfold_l_bracket` blind-resolves ONE bend. Slice #3 wires the
# proven unfold to REAL user-authored geometry (docs/design/sheet-metal.md §6): a
# base flange + N edge flanges, each bend tagged with a CylindricalFaceSignature at
# construction (§5), unfolded by PROVENANCE (find each bend face by its signature),
# not blind detection. v1 scope is a depth-1 PARALLEL bend star (§4.3) — every
# bend folds directly off the fixed base along a parallel axis, covering the
# L-bracket (N=1) and U-channel (N=2). A bend whose signature no longer resolves is
# an honest ``subshape_unresolved`` (via :func:`resolve_cylindrical_face`), never a
# wrong flat pattern.


@dataclass(frozen=True)
class BendProvenance:
    """One bend's construction-time provenance (§5): the cylindrical bend face's
    signature, the base flange face's signature (to separate base from the moving
    flange), and the bend's K-factor (inherited or overridden per-feature)."""

    cyl_signature: CylindricalFaceSignature
    base_face_signature: PlanarFaceSignature
    k_factor: float


@dataclass(frozen=True)
class _StarBend:
    """A resolved star bend, ready to lay out flat."""

    radius_mm: float
    angle_rad: float
    width_mm: float
    k_factor: float
    allowance_mm: float
    moving_leg_mm: float
    moving_area_mm2: float
    u_position: float  # moving flange centroid, projected on the layout u-axis
    side: int  # +1 extends +u beyond the base, -1 extends -u
    direction: Literal["up", "down"]  # fold sense relative to the base normal


def unfold_sheet_metal(
    body: BodyShape,
    bends: list[BendProvenance],
    thickness_mm: float,
    default_k_factor: float,
) -> FlatPattern:
    """Unfold an authored depth-1 parallel bend star into its :class:`FlatPattern`.

    Resolves each bend by its :class:`CylindricalFaceSignature` (§5), separates the
    shared base flange from each moving flange by the base face signature, and lays
    the developed blank out flat: the base flange in the middle, each flange folded
    down onto its side with the cylindrical bend region replaced by a bend-allowance
    strip (``BA = angle_rad * (radius + K * thickness)``, §1). Byte-deterministic
    (§9 #4): every value flows from a deterministic OCCT measurement + closed form.

    Raises:
        SubshapeUnresolvedError / SubshapeAmbiguousError: a bend signature no longer
            resolves against *body* (a dangling bend — §5 honest degradation).
        UnfoldStarError: the bends do not form a depth-1 PARALLEL star, or share no
            single base flange face (outside v1 scope).
    """
    if not bends:
        raise UnfoldStarError("An unfold needs at least one bend (edge flange).")

    # Resolve each bend ONCE by provenance: cylindrical face → geometry + flanges,
    # then separate the shared base from the moving flange by the base signature.
    # Each entry: (base_face, moving_face, axis_dir Vector, angle_rad, provenance).
    resolved = []
    for prov in bends:
        inner = resolve_cylindrical_face(body, prov.cyl_signature)
        rbf = resolve_bend_faces(body, inner)
        base_rec, moving_rec = _split_base_moving(rbf.flanges, prov.base_face_signature)
        axis_dir = Vector(*rbf.axis_dir).normalized()
        resolved.append((base_rec, moving_rec, axis_dir, rbf.angle_rad, prov))

    # The base flange is SHARED across every bend; take it from the first.
    base_rec = resolved[0][0]
    base_normal = Vector(*base_rec.normal).normalized()

    # Layout frame: v = the common bend axis (all parallel — v1 parallel-star
    # scope); u ⟂ v in the base plane.
    v0 = resolved[0][2]
    for _b, _m, axis_dir, _a, _p in resolved[1:]:
        if 1.0 - abs(v0.dot(axis_dir)) > _PARALLEL_TOL:
            raise UnfoldStarError(
                "The bends are not parallel; v1 unfolds a depth-1 PARALLEL bend "
                "star (L-bracket / U-channel). Non-parallel stars are deferred (§4.3)."
            )
    u_axis = v0.cross(base_normal).normalized()

    def proj_u(centroid: tuple[float, float, float]) -> float:
        return centroid[0] * u_axis.X + centroid[1] * u_axis.Y + centroid[2] * u_axis.Z

    base_center_u = proj_u(base_rec.centroid)
    base_len = base_rec.developed_length_mm

    star_bends: list[_StarBend] = []
    for _base_rec, moving_rec, _axis, angle_rad, prov in resolved:
        radius = prov.cyl_signature.radius_mm
        ba = bend_allowance(angle_rad, radius, prov.k_factor, thickness_mm)
        um = proj_u(moving_rec.centroid)
        # Fold sense: the moving flange centroid on the +normal side is "up".
        along_n = (
            (moving_rec.centroid[0] - base_rec.centroid[0]) * base_normal.X
            + (moving_rec.centroid[1] - base_rec.centroid[1]) * base_normal.Y
            + (moving_rec.centroid[2] - base_rec.centroid[2]) * base_normal.Z
        )
        star_bends.append(
            _StarBend(
                radius_mm=radius,
                angle_rad=angle_rad,
                width_mm=moving_rec.width_mm,
                k_factor=prov.k_factor,
                allowance_mm=ba,
                moving_leg_mm=moving_rec.developed_length_mm,
                moving_area_mm2=moving_rec.area_mm2,
                u_position=um,
                side=1 if um > base_center_u else -1,
                direction="up" if along_n >= 0.0 else "down",
            )
        )

    return _lay_out_star(
        star_bends,
        base_len=base_len,
        base_area=base_rec.area_mm2,
        base_width=base_rec.width_mm,
        thickness_mm=thickness_mm,
        default_k_factor=default_k_factor,
    )


def _split_base_moving(
    flanges: tuple[FlangeFaceRecord, FlangeFaceRecord],
    base_sig: PlanarFaceSignature,
) -> tuple[FlangeFaceRecord, FlangeFaceRecord]:
    """(base, moving) — the flange matching *base_sig* is the base, the other moves."""
    a, b = flanges
    if planar_signatures_match(a.signature, base_sig):
        return a, b
    if planar_signatures_match(b.signature, base_sig):
        return b, a
    raise UnfoldStarError(
        "Neither flanking face of a bend matches the stored base-flange face "
        "signature; the bend is not a depth-1 flange off the recorded base (§4.3)."
    )


def _lay_out_star(
    star_bends: list[_StarBend],
    *,
    base_len: float,
    base_area: float,
    base_width: float,
    thickness_mm: float,
    default_k_factor: float,
) -> FlatPattern:
    """Develop the base + flanges into a flat rectangular blank + tagged bend lines.

    Deterministic order: left (-u) bends outermost-first, then the base, then right
    (+u) bends nearest-first -- a pure function of each bend's u-position (RESEARCH
    §9). For the v1 parallel star with full-width flanges the blank is a rectangle
    (flat_length by base_width); each bend contributes one fold line."""
    left = sorted((b for b in star_bends if b.side < 0), key=lambda b: b.u_position)
    right = sorted((b for b in star_bends if b.side > 0), key=lambda b: b.u_position)

    width = base_width
    bend_lines: list[BendLine] = []
    fold_centers: list[float] = []
    u = 0.0
    index = 0

    def add_bend(b: _StarBend, strip_start: float) -> None:
        nonlocal index
        index += 1
        strip_end = strip_start + b.allowance_mm
        fold_centers.append(strip_start + b.allowance_mm / 2.0)
        bend_lines.append(
            BendLine(
                bend_id=f"bend-{index}",
                angle_deg=math.degrees(b.angle_rad),
                radius_mm=b.radius_mm,
                k_factor=b.k_factor,
                allowance_mm=b.allowance_mm,
                width_mm=b.width_mm,
                direction=b.direction,
                flat_start_mm=strip_start,
                flat_end_mm=strip_end,
            )
        )

    # Left flanges: [flange leg][BA strip] then the base.
    for b in left:
        u += b.moving_leg_mm
        add_bend(b, u)
        u += b.allowance_mm
    # Base flange.
    u += base_len
    # Right flanges: [BA strip][flange leg].
    for b in right:
        add_bend(b, u)
        u += b.allowance_mm + b.moving_leg_mm

    flat_length = u
    flat_area = base_area + sum(
        b.moving_area_mm2 + b.allowance_mm * b.width_mm for b in star_bends
    )

    fl = flat_length
    outline: list[FlatEdge2D] = [
        FlatEdge2D(kind="line", x1=0.0, y1=0.0, x2=fl, y2=0.0, role="body"),
        FlatEdge2D(kind="line", x1=fl, y1=0.0, x2=fl, y2=width, role="body"),
        FlatEdge2D(kind="line", x1=fl, y1=width, x2=0.0, y2=width, role="body"),
        FlatEdge2D(kind="line", x1=0.0, y1=width, x2=0.0, y2=0.0, role="body"),
    ]
    for cu in fold_centers:
        outline.append(
            FlatEdge2D(kind="line", x1=cu, y1=0.0, x2=cu, y2=width, role="bend")
        )

    # Deterministic bend-table order: by fold-line position along u.
    ordered = sorted(
        bend_lines, key=lambda bl: (bl.flat_start_mm + bl.flat_end_mm) / 2.0
    )

    return FlatPattern(
        thickness_mm=thickness_mm,
        k_factor=default_k_factor,
        flat_length_mm=flat_length,
        flat_area_mm2=flat_area,
        bend_width_mm=width,
        outline=tuple(outline),
        bends=tuple(ordered),
    )

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
from typing import Literal, cast

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
Vec3f = tuple[float, float, float]  #: A world-mm 3-tuple (kernel-free).
Vec2 = tuple[float, float]  #: A developed 2D point (mm).
#: A developed axis-aligned rectangle: (min_x, min_y, max_x, max_y). Defined here
#: (not beside the depth-2 tree code that first introduced it) so BOTH the
#: corner-relief path (§4.4) and the depth-2 tree path can annotate with it —
#: module-level annotations evaluate at import, so the alias must precede its first
#: use (`_rect_from_ranges`), not just its textually-first use.
_Rect = tuple[float, float, float, float]
_PARALLEL_TOL = 1e-9  # 1 - |dot| between unit axis directions
#: Axis-alignment tolerance for the non-parallel (2D) layout: a bend axis or a
#: base edge must be parallel/perpendicular to the base rectangle frame to within
#: this |dot| residual. Authored sheets are axis-aligned, so residuals are
#: ulp-scale; loose enough to absorb kernel jitter, tight enough that an angled
#: flange is an honest out-of-scope raise, never a silently mislaid arm.
_ALIGN_TOL = 1e-7


class UnfoldScopeError(SheetMetalUnfoldError):
    """The body is outside SPIKE 0's single-bend L-bracket scope."""


class UnfoldStarError(SheetMetalUnfoldError):
    """The body is outside the supported sheet-metal unfold scope
    (docs/design/sheet-metal.md §4.3). The unfold handles a depth-1 bend STAR (N
    edge flanges folded directly off ONE fixed base — L-bracket / U-channel 1D
    strip, or a tray / pan 2D plus off a rectangular base) AND a depth-≥2 bend TREE
    (a flange folded off ANOTHER flange — a box corner / return / parallel Z-chain)
    that develops without self-overlap. Still raised here (genuinely unsupported): a
    non-rectangular or angled base, a bend axis not aligned to the base rectangle,
    a bend set that is not a single tree rooted at one base flange (disconnected /
    cyclic), or a NON-axis-aligned intermediate flange in a depth-≥2 tree (the
    shipped emitter lays out axis-aligned rectangles only; the general 2D placement
    is a documented follow-on, §4.3). A depth-≥2 development that self-OVERLAPS is
    the sibling :class:`UnfoldOverlapError` (a shape needing corner relief, §7)."""


class UnfoldOverlapError(SheetMetalUnfoldError):
    """The developed flat pattern SELF-OVERLAPS — two flange regions collide in 2D
    (docs/design/sheet-metal.md §4.3 / §7). This is the load-bearing correctness
    gate for the depth-≥2 tree unfold: a full multi-sided box whose corners
    geometrically require RELIEF (§7, deferred) develops into overlapping material
    that cannot be cut as a single flat blank. Rather than emit a silently-wrong /
    overlapping pattern, the unfold refuses with this typed error (the honest-
    degradation contract, §5). Corner relief itself stays out of v1 scope; this
    feature UNFOLDS a chain and REJECTS (typed) the cases that need relief."""


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
class CornerRelief:
    """An explicit RECTANGULAR corner relief at a bend INTERSECTION (§4.4).

    Names the two bends whose shared corner it relieves (by their construction-time
    :class:`CylindricalFaceSignature`, §5) + the absolute notch ``size_mm``
    (``relief_ratio x thickness``, default ratio 1.0, resolved by the authoring
    layer, §4.4.3). ``relief_type`` is ``"rectangular"`` in v1 (the only purely-
    rectilinear developable notch — obround/round/tear are §4.4.1 follow-ons). The
    SAME spec drives the 3D boolean (:func:`geometry.sheet_metal.corner_relief.
    apply_corner_relief`) and the flat-pattern notch (:func:`unfold_sheet_metal`),
    so the manufacturable body and the blank are consistent by construction."""

    bend_a: CylindricalFaceSignature
    bend_b: CylindricalFaceSignature
    size_mm: float
    relief_type: Literal["rectangular"] = "rectangular"


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
    reliefs: list[CornerRelief] | None = None,
) -> FlatPattern:
    """Unfold an authored depth-1 bend star into its :class:`FlatPattern`.

    Resolves each bend by its :class:`CylindricalFaceSignature` (§5), separates the
    shared base flange from each moving flange by the base face signature, and lays
    the developed blank out flat: the base flange in the middle, each flange folded
    down onto its side with the cylindrical bend region replaced by a bend-allowance
    strip (``BA = angle_rad * (radius + K * thickness)``, §1). All-parallel bend
    axes develop as a 1D strip (L-bracket / U-channel); non-parallel axes off a
    rectangular base develop as a 2D plus/cross (a tray / pan). Byte-deterministic
    (§9 #4): every value flows from a deterministic OCCT measurement + closed form.

    Raises:
        SubshapeUnresolvedError / SubshapeAmbiguousError: a bend signature no longer
            resolves against *body* (a dangling bend — §5 honest degradation).
        UnfoldStarError: the bends do not form a depth-1 star off ONE shared base
            flange — including ANY depth >= 2 body (a flange folded off another
            flange), rejected uniformly ahead of layout so no authored body leaks a
            raw kernel exception — or a non-rectangular / axis-unaligned base
            (outside v1 scope, §4.3).
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

    # The base flange is SHARED across every bend; take it from the first. The
    # first-authored bend always folds directly off the base (a depth-2 flange
    # references an earlier flange's edge, so it is authored AFTER its parent),
    # so resolved[0][0] is the true fixed base.
    base_rec = resolved[0][0]
    base_normal = Vector(*base_rec.normal).normalized()

    # DEPTH DISPATCH (§4.3): a depth-1 bend STAR — every bend folds directly off the
    # ONE shared base flange — lays out with the pinned 1D-strip / 2D-plus special
    # cases below (their committed goldens stay BYTE-IDENTICAL). A bend whose
    # resolved base face is NOT that shared base is a flange folded off ANOTHER
    # flange — depth >= 2 (a box corner / return / Z-chain) — which now routes to
    # the general bend-TREE walk (:func:`_unfold_bend_tree`), graduated from the
    # tractability spike (the uniform depth-2 rejection is LIFTED for the cases that
    # develop without self-overlap; genuinely-unsupported depth-2 stays a typed
    # `UnfoldStarError` / `UnfoldOverlapError`). This dispatch never fires the tree
    # path for a genuine depth-1 star — every edge flange there records the shared
    # base's signature, so all bases match and the L-bracket / U-channel / tray
    # goldens are unaffected.
    base_sig = base_rec.signature
    is_depth1 = all(
        planar_signatures_match(other_base.signature, base_sig)
        for other_base, _m, _axis, _a, _p in resolved[1:]
    )
    if not is_depth1:
        if reliefs:
            # v1 corner relief scopes to the depth-1 adjacent-flange tray corner
            # (§4.4.4). A depth-≥2 (welded / returns) box corner is a cyclic /
            # coplanar degeneracy a rectangular notch does NOT lift — that needs
            # miter / closed-corner geometry (deferred) — so it stays a typed
            # reject rather than a silently-wrong relieved blank.
            raise UnfoldStarError(
                "Corner relief v1 applies to a depth-1 adjacent-flange tray corner; "
                "the body is depth >= 2 (a flange folded off another flange). A "
                "rectangular notch does not make a fully-welded box corner "
                "developable — that needs miter / closed-corner geometry (§4.4.4)."
            )
        return _unfold_bend_tree(body, bends, thickness_mm, default_k_factor)

    if reliefs:
        # A relieved depth-1 tray develops through the corner-relief path (§4.4):
        # each named corner loses a size x size square, the two adjacent flanges are
        # inset, and the outline gains the reentrant notch. Only runs when a relief
        # is supplied, so every non-relieved golden takes the verbatim paths below.
        return _unfold_nonparallel_relieved(
            resolved, base_rec, thickness_mm, default_k_factor, reliefs
        )

    # A depth-1 star is PARALLEL (all bend axes share one direction → a 1D strip,
    # the L-bracket / U-channel) or NON-PARALLEL (flanges off perpendicular edges
    # of a rectangular base → a 2D plus/cross, a tray / pan). Both flatten each
    # flange independently against the fixed base (no graph relaxation, §4.3); they
    # differ only in the layout dimensionality. The parallel path is kept verbatim
    # so its committed goldens stay byte-identical.
    v0 = resolved[0][2]
    all_parallel = all(
        1.0 - abs(v0.dot(axis_dir)) <= _PARALLEL_TOL
        for _b, _m, axis_dir, _a, _p in resolved[1:]
    )
    if all_parallel:
        return _unfold_parallel(
            resolved, base_rec, base_normal, thickness_mm, default_k_factor
        )
    return _unfold_nonparallel(
        resolved, base_rec, base_normal, thickness_mm, default_k_factor
    )


#: Type alias for a resolved bend: (base_rec, moving_rec, axis_dir, angle_rad, prov).
_Resolved = tuple[FlangeFaceRecord, FlangeFaceRecord, Vector, float, BendProvenance]
#: A 2D outline segment in frame coords: (x1, y1, x2, y2, role).
_Seg = tuple[float, float, float, float, str]


def _unfold_parallel(
    resolved: list[_Resolved],
    base_rec: FlangeFaceRecord,
    base_normal: Vector,
    thickness_mm: float,
    default_k_factor: float,
) -> FlatPattern:
    """Lay out an all-parallel depth-1 star as a 1D strip (L-bracket / U-channel).

    Kept verbatim from the v1 parallel implementation so its committed goldens
    stay byte-identical: v = the common bend axis, u ⟂ v in the base plane, and
    every flange projects onto u to a side of the fixed base."""
    v0 = resolved[0][2]
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


# --- Non-parallel depth-1 star (sheet-metal v2 #1) — a 2D plus/cross layout ------
#
# A depth-1 star whose bend axes are NOT all parallel (a tray / pan: a base + N
# edge flanges off perpendicular edges) lays out in 2D, not along a single strip:
# each flange swings flat about its OWN bend axis into the base plane, extending
# OUTWARD along its own edge's direction. Because every flange folds independently
# off the FIXED base (depth 1, §4.3), each arm is placed analytically against the
# base rectangle with no graph relaxation — the same closed-form bend allowance,
# now positioned in the plane instead of on a line. The blank is a plus/cross with
# reentrant corners where perpendicular arms meet; those corners are disjoint in
# 2D (each arm occupies its own cardinal quadrant of the plane) and the built 3D
# body has exactly-additive volume (verified), so shared-corner flanges are IN
# scope — corner reliefs stay a documented deferral (§7). v1 scopes the base to a
# RECTANGLE with axis-aligned bends (a tray); a non-rectangular / angled base is
# an honest UnfoldStarError.


def _canonical_dir(v: Vector) -> Vector:
    """A sign-canonical unit direction: flip so the largest-magnitude component is
    positive (deterministic frame axis, independent of edge/vertex orientation)."""
    comps = sorted(((abs(v.X), 0), (abs(v.Y), 1), (abs(v.Z), 2)))
    idx = comps[-1][1]
    comp = (v.X, v.Y, v.Z)[idx]
    return v if comp >= 0.0 else v * -1.0


@dataclass(frozen=True)
class _BaseFrame:
    """A rectangular base flange's in-plane 2D frame: two perpendicular unit axes
    (world) + the min-corner offsets so any base point projects into ``[0, wx] x
    [0, wy]``. The layout origin never depends on face iteration order."""

    x2: Vector
    y2: Vector
    normal: Vector
    x_min: float
    y_min: float
    wx: float
    wy: float

    def to2d(self, p: tuple[float, float, float]) -> tuple[float, float]:
        v = Vector(*p)
        return (v.dot(self.x2) - self.x_min, v.dot(self.y2) - self.y_min)


def _base_frame(base_rec: FlangeFaceRecord) -> _BaseFrame:
    """Deterministic 2D frame of a RECTANGULAR base face (v1 non-parallel scope).

    Raises UnfoldStarError if the base has other than two perpendicular edge
    directions (a non-rectangular or angled base is out of scope)."""
    normal = _canonical_dir(Vector(*base_rec.normal).normalized())
    dirs: list[Vector] = []
    for edge in base_rec.face.edges():
        delta = (edge @ 1.0) - (edge @ 0.0)
        if delta.length < 1e-9:
            continue
        d = _canonical_dir(delta.normalized())
        if not any(1.0 - abs(d.dot(x)) <= _ALIGN_TOL for x in dirs):
            dirs.append(d)
    if len(dirs) != 2:
        raise UnfoldStarError(
            f"The non-parallel unfold requires a RECTANGULAR base flange; its face "
            f"has {len(dirs)} distinct edge directions. A non-rectangular / angled "
            "base is a documented next increment (§4.3)."
        )
    dirs.sort(key=lambda d: (round(d.X, 9), round(d.Y, 9), round(d.Z, 9)))
    x2, y2 = dirs[0], dirs[1]
    if abs(x2.dot(y2)) > _ALIGN_TOL:
        raise UnfoldStarError(
            "The base flange's edge directions are not perpendicular; v1's "
            "non-parallel unfold scopes to a rectangular base (§4.3)."
        )
    verts = [Vector(v.X, v.Y, v.Z) for v in base_rec.face.vertices()]
    px = [v.dot(x2) for v in verts]
    py = [v.dot(y2) for v in verts]
    return _BaseFrame(
        x2=x2,
        y2=y2,
        normal=normal,
        x_min=min(px),
        y_min=min(py),
        wx=max(px) - min(px),
        wy=max(py) - min(py),
    )


@dataclass(frozen=True)
class _Arm:
    """One flange laid out flat as an axis-aligned arm off a base-rectangle side.

    ``axis`` 0 = the arm extends along the frame X axis, 1 = along Y; ``sign`` is
    its outward direction. ``span`` is the arm's extent along the fold edge (the
    base-edge direction). ``fold`` is the fold-edge coordinate (0 or wx/wy).
    ``bend_centroid`` is the resolved bend's cylindrical-face centroid — the key
    the corner-relief path (§4.4) matches a :class:`CornerRelief`'s named bends
    back onto the arm they trim; it is unused by the non-relieved emit + the arm
    sort key, so it never perturbs the byte-identical plus-pattern output."""

    axis: int
    sign: int
    fold: float
    span0: float
    span1: float
    allowance_mm: float
    leg_mm: float
    area_mm2: float
    width_mm: float
    radius_mm: float
    angle_rad: float
    k_factor: float
    direction: Literal["up", "down"]
    bend_centroid: Vec3f = (0.0, 0.0, 0.0)


def _build_arms(
    resolved: list[_Resolved],
    base_rec: FlangeFaceRecord,
    thickness_mm: float,
) -> tuple[_BaseFrame, list[_Arm]]:
    """Place each depth-1 non-parallel flange as an axis-aligned arm off the base.

    The shared arm-construction step of the non-parallel tray unfold (§6) and its
    corner-relief sibling (§4.4) — one source of the fold-direction / axis-alignment
    guards + the per-arm span math, so both paths agree. Returns the deterministic
    base frame + the arms in INPUT order (each caller sorts as it emits)."""
    frame = _base_frame(base_rec)
    base_c = Vector(*base_rec.centroid)

    arms: list[_Arm] = []
    for _brec, moving_rec, axis_dir, angle_rad, prov in resolved:
        e = axis_dir.normalized()
        radius = prov.cyl_signature.radius_mm
        ba = bend_allowance(angle_rad, radius, prov.k_factor, thickness_mm)
        # Belt-and-suspenders (the shared-base guard in `unfold_sheet_metal` already
        # rejects every depth-2 body before we reach here): a bend axis must be
        # PERPENDICULAR to the base normal to lie in the base plane. A parallel axis
        # (a box corner's vertical second bend) would make `e.cross(frame.normal)`
        # degenerate to a zero vector, so guard it as a typed error rather than let
        # `.normalized()` leak a raw kernel `Standard_ConstructionError` (§5).
        if abs(e.dot(frame.normal)) > _ALIGN_TOL:
            raise UnfoldStarError(
                "A bend axis is not perpendicular to the base flange normal (a flange "
                "folded off another flange — depth >= 2, a box corner). v1's "
                "non-parallel unfold scopes to depth-1 bends off the shared base "
                "(§4.3); depth-2 graph relaxation is deferred (§2.2 / §7)."
            )
        # Outward direction in the base plane, pointing away from the base interior.
        outward = e.cross(frame.normal).normalized()
        if (Vector(*moving_rec.centroid) - base_c).dot(outward) < 0.0:
            outward = outward * -1.0
        ox, oy = outward.dot(frame.x2), outward.dot(frame.y2)
        if abs(abs(ox) - 1.0) <= _ALIGN_TOL and abs(oy) <= _ALIGN_TOL:
            axis, sign = 0, 1 if ox > 0 else -1
            edge_dir = frame.y2
        elif abs(abs(oy) - 1.0) <= _ALIGN_TOL and abs(ox) <= _ALIGN_TOL:
            axis, sign = 1, 1 if oy > 0 else -1
            edge_dir = frame.x2
        else:
            raise UnfoldStarError(
                "A bend axis is not aligned to the base rectangle (an angled "
                "flange); v1's non-parallel unfold scopes to axis-aligned bends "
                "off a rectangular base (§4.3)."
            )
        # The arm's extent along the fold edge, from the moving flange's own
        # vertices (fold about the bend axis preserves the along-axis coordinate).
        edge_min = frame.x_min if axis == 1 else frame.y_min
        proj = [
            Vector(v.X, v.Y, v.Z).dot(edge_dir) - edge_min
            for v in moving_rec.face.vertices()
        ]
        along_n = (Vector(*moving_rec.centroid) - base_c).dot(frame.normal)
        arms.append(
            _Arm(
                axis=axis,
                sign=sign,
                fold=(frame.wx if axis == 0 else frame.wy) if sign > 0 else 0.0,
                span0=min(proj),
                span1=max(proj),
                allowance_mm=ba,
                leg_mm=moving_rec.developed_length_mm,
                area_mm2=moving_rec.area_mm2,
                width_mm=max(proj) - min(proj),
                radius_mm=radius,
                angle_rad=angle_rad,
                k_factor=prov.k_factor,
                direction="up" if along_n >= 0.0 else "down",
                bend_centroid=(
                    prov.cyl_signature.centroid.x,
                    prov.cyl_signature.centroid.y,
                    prov.cyl_signature.centroid.z,
                ),
            )
        )
    return frame, arms


def _unfold_nonparallel(
    resolved: list[_Resolved],
    base_rec: FlangeFaceRecord,
    base_normal: Vector,
    thickness_mm: float,
    default_k_factor: float,
) -> FlatPattern:
    """Lay out a NON-PARALLEL depth-1 star (a tray / pan) as a 2D plus/cross.

    Each flange is placed as an axis-aligned arm off its base-rectangle side, the
    cylindrical bend replaced by a ``BA``-length strip (§1). Area is the §9
    invariant (base counted once + Σ flange areas + Σ bend-strip areas); the
    outline is the union boundary (base free edges + each arm's three outer edges +
    one fold line per bend). Byte-deterministic: arms are sorted by a canonical
    (axis, sign, span) key, independent of the input bend order."""
    frame, arms = _build_arms(resolved, base_rec, thickness_mm)

    # Deterministic order: by (axis, outward sign, position along the fold edge).
    arms.sort(key=lambda a: (a.axis, a.sign, a.span0, a.span1))

    return _emit_plus_pattern(
        arms,
        frame,
        thickness_mm=thickness_mm,
        default_k_factor=default_k_factor,
        base_area=base_rec.area_mm2,
    )


#: Endpoint-coincidence tolerance for the closed-loop outline guard (mm). The
#: outline endpoints are exact frame coordinates (shifted by a common offset), so
#: matching residuals are ulp-scale; this bound is far tighter than the kernel
#: linear tolerance yet loose enough to absorb FP addition noise.
_LOOP_TOL_MM = 1e-6


def _body_outline_is_closed_loop(outline: list[FlatEdge2D]) -> bool:
    """True if the ``role="body"`` edges chain end-to-end into ONE closed loop.

    A pure endpoint-adjacency walk (no kernel call): start at the first body edge
    and repeatedly step to the unique unused edge sharing the current endpoint. The
    outline is a single closed loop iff every body edge is consumed exactly once and
    the walk returns to its start. Used to guard the full-width-flange assumption in
    :func:`_emit_plus_pattern` — a partial-width flange leaves a gap, breaking the
    walk, and is reported as a typed error rather than a silently non-closed blank."""
    segs = [((e.x1, e.y1), (e.x2, e.y2)) for e in outline if e.role == "body"]
    if not segs:
        return False
    used = [False] * len(segs)
    used[0] = True
    start, tail = segs[0]
    for _ in range(len(segs) - 1):
        nxt: tuple[float, float] | None = None
        for i, (a, b) in enumerate(segs):
            if used[i]:
                continue
            if math.dist(tail, a) <= _LOOP_TOL_MM:
                nxt, used[i] = b, True
                break
            if math.dist(tail, b) <= _LOOP_TOL_MM:
                nxt, used[i] = a, True
                break
        if nxt is None:
            return False
        tail = nxt
    return all(used) and math.dist(tail, start) <= _LOOP_TOL_MM


def _emit_plus_pattern(
    arms: list[_Arm],
    frame: _BaseFrame,
    *,
    thickness_mm: float,
    default_k_factor: float,
    base_area: float,
) -> FlatPattern:
    """Assemble the plus/cross outline + bend table from the placed arms.

    Coordinates are shifted so the whole blank sits in the positive quadrant with
    its bounding box at the origin — ``flat_length_mm`` / ``bend_width_mm`` are the
    bbox extents (for a rectangular parallel blank these equal the strip length /
    width, but that path never reaches here)."""
    # Collect every arm's outer geometry in frame coords, then shift to origin.
    raw: list[_Seg] = []
    fold_sides: set[tuple[int, int]] = set()

    for a in arms:
        fold_sides.add((a.axis, a.sign))
        near = a.fold
        far = near + a.sign * (a.allowance_mm + a.leg_mm)
        fold_c = near + a.sign * (a.allowance_mm / 2.0)
        if a.axis == 0:  # arm along X; spans [span0, span1] in Y
            raw.append((near, a.span0, far, a.span0, "body"))  # side
            raw.append((near, a.span1, far, a.span1, "body"))  # side
            raw.append((far, a.span0, far, a.span1, "body"))  # far edge
            raw.append((fold_c, a.span0, fold_c, a.span1, "bend"))
        else:  # arm along Y; spans [span0, span1] in X
            raw.append((a.span0, near, a.span0, far, "body"))
            raw.append((a.span1, near, a.span1, far, "body"))
            raw.append((a.span0, far, a.span1, far, "body"))
            raw.append((a.span0, fold_c, a.span1, fold_c, "bend"))

    # Base rectangle's four sides; a side with a flange is a fold (skipped as a
    # body edge — the arm continues the material there), else a real cut edge.
    # (axis, sign) -> the side: X/+ = right (x=wx), X/- = left (x=0), Y/+ = top,
    # Y/- = bottom.
    # FULL-WIDTH ASSUMPTION (guarded below): skipping a whole base side is only
    # correct when the arm on it spans the ENTIRE edge (its span reaches both base
    # corners), so the arm's side edges meet the neighbouring sides/arms and the
    # union boundary stays a single closed loop. Every authorable edge flange today
    # is full-width (the edge-flange feature folds off a whole base edge), so this
    # holds. A future partial-width / offset flange would leave a gap on the skipped
    # side — a NON-closed outline — which the closed-loop guard after assembly
    # catches as a typed error rather than emitting a silently broken blank.
    wx, wy = frame.wx, frame.wy
    base_sides: dict[tuple[int, int], _Seg] = {
        (0, 1): (wx, 0.0, wx, wy, "body"),
        (0, -1): (0.0, 0.0, 0.0, wy, "body"),
        (1, 1): (0.0, wy, wx, wy, "body"),
        (1, -1): (0.0, 0.0, wx, 0.0, "body"),
    }
    for side, seg in base_sides.items():
        if side not in fold_sides:
            raw.append(seg)

    # Shift so the bounding box's min corner is the origin (all coords >= 0).
    xs = [c for s in raw for c in (s[0], s[2])]
    ys = [c for s in raw for c in (s[1], s[3])]
    dx, dy = min(xs), min(ys)
    outline: list[FlatEdge2D] = [
        FlatEdge2D(
            kind="line",
            x1=s[0] - dx,
            y1=s[1] - dy,
            x2=s[2] - dx,
            y2=s[3] - dy,
            role=cast(Literal["body", "bend"], s[4]),
        )
        for s in raw
    ]
    # Deterministic outline order: body edges then bend edges, each by endpoints.
    outline.sort(key=lambda e: (e.role, e.x1, e.y1, e.x2, e.y2))

    # Guard the full-width assumption (above): the body edges MUST chain into one
    # closed loop. For every v1-authorable tray they do (full-width arms meet at the
    # base corners); a future partial/offset flange would break it, and we fail typed
    # here (§5) rather than emit a silently non-closed blank a shop would mis-cut.
    if not _body_outline_is_closed_loop(outline):
        raise UnfoldStarError(
            "The developed outline is not a single closed loop — a flange does not "
            "span its full base edge (a partial / offset flange). v1's non-parallel "
            "unfold assumes full-width edge flanges (§4.3 / §7 deferred)."
        )

    bend_lines: list[BendLine] = []
    for i, a in enumerate(arms, start=1):
        near = a.fold
        s0 = near + a.sign * 0.0
        s1 = near + a.sign * a.allowance_mm
        lo, hi = sorted((s0, s1))
        shift = dx if a.axis == 0 else dy
        bend_lines.append(
            BendLine(
                bend_id=f"bend-{i}",
                angle_deg=math.degrees(a.angle_rad),
                radius_mm=a.radius_mm,
                k_factor=a.k_factor,
                allowance_mm=a.allowance_mm,
                width_mm=a.width_mm,
                direction=a.direction,
                flat_start_mm=lo - shift,
                flat_end_mm=hi - shift,
            )
        )

    flat_area = base_area + sum(a.area_mm2 + a.allowance_mm * a.width_mm for a in arms)
    return FlatPattern(
        thickness_mm=thickness_mm,
        k_factor=default_k_factor,
        flat_length_mm=max(xs) - min(xs),
        flat_area_mm2=flat_area,
        bend_width_mm=max(ys) - min(ys),
        outline=tuple(outline),
        bends=tuple(bend_lines),
    )


# --- Corner relief (§4.4): the relieved depth-1 tray flat pattern ------------------
#
# A relieved tray corner loses a size x size square of material at the shared base
# corner of two adjacent perpendicular flanges; each flange (+ its BA strip) is
# inset by `size` at that end. In the developed frame this is a set of axis-aligned
# rectangles — the base decomposed to avoid every notched corner + the inset flange
# legs + the inset BA strips — which the shipped `_rectilinear_union_loop` (§4.3)
# unions into ONE closed loop with a reentrant right-angle notch. Only runs when a
# relief is supplied (`unfold_sheet_metal(..., reliefs=...)`), so every non-relieved
# golden takes the verbatim plus-pattern / strip / tree paths above (byte-identical).

#: Bend-centroid match tolerance (mm) — a CornerRelief's named bend signature is the
#: SAME construction-time centroid the arm carries, so residuals are ulp-scale.
_RELIEF_MATCH_TOL_MM = 1e-6


def _arm_index_for_bend(arms: list[_Arm], centroid: Vec3f) -> int:
    """The index of the arm whose bend cylindrical-face centroid matches *centroid*.

    Matches a :class:`CornerRelief`'s named bend back to the arm it trims. Exactly
    one within tolerance, or a typed error — the same refuse-to-guess rule (§5)."""
    hits = [
        i
        for i, a in enumerate(arms)
        if math.dist(a.bend_centroid, centroid) <= _RELIEF_MATCH_TOL_MM
    ]
    if len(hits) != 1:
        raise UnfoldStarError(
            f"A corner relief names a bend that matches {len(hits)} of the body's "
            "edge flanges by centroid; the relieved corner is unresolved (§4.4). "
            "Each relief must name two distinct depth-1 flanges of THIS tray."
        )
    return hits[0]


def _rect_from_ranges(x0: float, x1: float, y0: float, y1: float) -> _Rect:
    """An axis-aligned rectangle from two (unordered) coordinate ranges."""
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _base_minus_notches_rects(
    wx: float, wy: float, notches: list[_Rect]
) -> list[_Rect]:
    """Decompose ``[0,wx]x[0,wy]`` minus the corner *notches* into a grid of rects.

    Each notch is a corner square of the base; the base coordinate grid (0, wx, wy
    + every notch inner edge) tiles the base into cells, and a cell is kept iff its
    centre is inside the base and outside every notch. The kept cells feed the same
    rectilinear union the arms do (§4.3) — the union re-merges them into the L /
    stepped outline, so this never emits a spurious internal seam."""
    xs = sorted({0.0, wx} | {c for n in notches for c in (n[0], n[2])})
    ys = sorted({0.0, wy} | {c for n in notches for c in (n[1], n[3])})
    cells: list[_Rect] = []
    for i in range(len(xs) - 1):
        cx = (xs[i] + xs[i + 1]) / 2.0
        for j in range(len(ys) - 1):
            cy = (ys[j] + ys[j + 1]) / 2.0
            if not (0.0 <= cx <= wx and 0.0 <= cy <= wy):
                continue
            if any(n[0] < cx < n[2] and n[1] < cy < n[3] for n in notches):
                continue
            cells.append((xs[i], ys[j], xs[i + 1], ys[j + 1]))
    return cells


@dataclass
class _ArmTrim:
    """An arm's span endpoints after corner-relief trims (mutable accumulation)."""

    lo: float
    hi: float


def _unfold_nonparallel_relieved(
    resolved: list[_Resolved],
    base_rec: FlangeFaceRecord,
    thickness_mm: float,
    default_k_factor: float,
    reliefs: list[CornerRelief],
) -> FlatPattern:
    """Lay out a RELIEVED depth-1 tray (§4.4): the plus-pattern with corner notches.

    Each relief removes a ``size x size`` square at the shared base corner of its two
    named flanges and insets both flanges (+ their BA strips) there. The base
    (minus notches) + inset legs + inset strips are unioned into ONE closed loop with
    the reentrant notch. Byte-deterministic (§9 #4): every value is a deterministic
    OCCT measurement + closed-form allowance + a coordinate-sorted assembly.

    Raises:
        UnfoldStarError: a relief names a bend not on this tray, names two parallel
            (non-adjacent) flanges, or the relieved outline is not a single loop
            (§4.4 v1 scope: rectangular relief at an adjacent-flange corner)."""
    frame, arms = _build_arms(resolved, base_rec, thickness_mm)
    wx, wy = frame.wx, frame.wy

    trims = [_ArmTrim(a.span0, a.span1) for a in arms]
    notches: list[_Rect] = []
    for relief in reliefs:
        ca, cb = relief.bend_a.centroid, relief.bend_b.centroid
        i = _arm_index_for_bend(arms, (ca.x, ca.y, ca.z))
        j = _arm_index_for_bend(arms, (cb.x, cb.y, cb.z))
        ai, aj = arms[i], arms[j]
        if ai.axis == aj.axis:
            raise UnfoldStarError(
                "A corner relief names two flanges on parallel edges; a corner is a "
                "bend INTERSECTION of two PERPENDICULAR flanges (§4.4)."
            )
        size = relief.size_mm
        # The shared base corner: each arm's fold is a base side (0 or wx/wy) on the
        # OTHER arm's span axis. arm with axis==1 spans X, folds along a Y side; its
        # relief partner (axis==0) folds along an X side = the corner's X coordinate.
        arm_x = ai if ai.axis == 0 else aj  # spans Y, fold is an X coordinate
        arm_y = ai if ai.axis == 1 else aj  # spans X, fold is a Y coordinate
        corner_x, corner_y = arm_x.fold, arm_y.fold
        notches.append(
            _rect_from_ranges(
                corner_x - size if corner_x > 0.0 else 0.0,
                corner_x if corner_x > 0.0 else size,
                corner_y - size if corner_y > 0.0 else 0.0,
                corner_y if corner_y > 0.0 else size,
            )
        )
        # Inset each flange's span by `size` at the corner end (the span end nearest
        # the corner coordinate on that arm's span axis).
        for ti, corner_coord in (
            (trims[i if ai.axis == 0 else j], corner_y),  # arm_x spans Y
            (trims[i if ai.axis == 1 else j], corner_x),  # arm_y spans X
        ):
            if abs(corner_coord - ti.hi) <= abs(corner_coord - ti.lo):
                ti.hi -= size
            else:
                ti.lo += size

    # Assemble every developed rectangle in frame coords: base cells (minus notches),
    # then each arm's inset BA strip + leg.
    rects: list[_Rect] = _base_minus_notches_rects(wx, wy, notches)
    for a, ti in zip(arms, trims, strict=True):
        lo, hi = ti.lo, ti.hi
        near = a.fold
        strip_far = near + a.sign * a.allowance_mm
        leg_far = near + a.sign * (a.allowance_mm + a.leg_mm)
        if a.axis == 0:  # spans Y in [lo, hi], extends along X
            strip = _rect_from_ranges(near, strip_far, lo, hi)
            leg = _rect_from_ranges(strip_far, leg_far, lo, hi)
        else:  # spans X in [lo, hi], extends along Y
            strip = _rect_from_ranges(lo, hi, near, strip_far)
            leg = _rect_from_ranges(lo, hi, strip_far, leg_far)
        rects.append(strip)
        rects.append(leg)

    snapped = _snap_rects(rects)
    loop = _rectilinear_union_loop(snapped)
    dx = min(p[0] for p in loop)
    dy = min(p[1] for p in loop)
    loop = [(p[0] - dx, p[1] - dy) for p in loop]
    all_x = [p[0] for p in loop]
    all_y = [p[1] for p in loop]

    outline: list[FlatEdge2D] = []
    n = len(loop)
    for k in range(n):
        x1, y1 = loop[k]
        x2, y2 = loop[(k + 1) % n]
        outline.append(FlatEdge2D(kind="line", x1=x1, y1=y1, x2=x2, y2=y2, role="body"))

    bend_lines: list[BendLine] = []
    for idx, (a, ti) in enumerate(zip(arms, trims, strict=True), start=1):
        span_shift = dx if a.axis == 1 else dy
        lo, hi = ti.lo - span_shift, ti.hi - span_shift
        near = a.fold
        fold_c = near + a.sign * (a.allowance_mm / 2.0)
        if a.axis == 0:  # vertical fold centerline at X=fold_c, over Y span
            xm = fold_c - dx
            outline.append(
                FlatEdge2D(kind="line", x1=xm, y1=lo, x2=xm, y2=hi, role="bend")
            )
        else:  # horizontal fold centerline at Y=fold_c, over X span
            ym = fold_c - dy
            outline.append(
                FlatEdge2D(kind="line", x1=lo, y1=ym, x2=hi, y2=ym, role="bend")
            )
        bend_lines.append(
            BendLine(
                bend_id=f"bend-{idx}",
                angle_deg=math.degrees(a.angle_rad),
                radius_mm=a.radius_mm,
                k_factor=a.k_factor,
                allowance_mm=a.allowance_mm,
                width_mm=abs(ti.hi - ti.lo),
                direction=a.direction,
                flat_start_mm=0.0,
                flat_end_mm=a.allowance_mm,
            )
        )

    outline.sort(key=lambda e: (e.role, e.x1, e.y1, e.x2, e.y2))
    bend_lines.sort(key=lambda bl: bl.bend_id)

    base_area = wx * wy - sum((rr[2] - rr[0]) * (rr[3] - rr[1]) for rr in notches)
    flat_area = base_area + sum(
        abs(t.hi - t.lo) * (a.leg_mm + a.allowance_mm)
        for a, t in zip(arms, trims, strict=True)
    )
    return FlatPattern(
        thickness_mm=thickness_mm,
        k_factor=default_k_factor,
        flat_length_mm=max(all_x) - min(all_x),
        flat_area_mm2=flat_area,
        bend_width_mm=max(all_y) - min(all_y),
        outline=tuple(outline),
        bends=tuple(bend_lines),
    )


# --- Depth-≥2 bend TREE unfold (graduated from the tractability spike) -------------
#
# A depth-≥2 body — a flange folded off ANOTHER flange (a box corner / return / hat
# channel / parallel Z-chain) — unfolds by a recursive-compositional tree walk (the
# spike proved this TRACTABLE, docs/design/sheet-metal.md §4.3): build the bend tree
# (each bend oriented parent→child by its recorded `base_face_signature`, §5), place
# the base flange at identity, then walk outward placing each child flange IN ITS
# PARENT'S ALREADY-FLATTENED 2D frame — `child_2d = parent_2d(cpP) + BA·w_parent_2d`.
# Because the parent's map is already composed, the walk composes transforms EXACTLY
# (no relaxation, no iteration, no error accumulation beyond FP). This is the frame
# math the isolated `_spike_bend_chain` module validated, now folded into the shipped
# path (DRY — one implementation) and extended with the two feature-level pieces the
# spike deferred: (a) a SINGLE union outline (a closed rectilinear loop the way
# `_emit_plus_pattern` builds the depth-1 plus, not per-flange rectangles), and
# (b) a self-OVERLAP gate (`UnfoldOverlapError`) for developments that need corner
# relief (§7). The depth-1 star keeps its own pinned layout above (byte-identical).

#: A flat face's in-run identity key (outward normal + area centroid, rounded to the
#: subshape linear tolerance) so the bend tree's nodes are stable and hashable — a
#: depth-2 chain's middle flange is the SAME node across the two bends that share it.
#: NOT a persisted identity (RESEARCH §9: never quantize a stored id) — an in-run
#: graph key only.
_KEY_NORMAL_DP = 6
_KEY_CENTROID_DP = 4
#: Axis-aligned-rectangle residual for a developed flange/strip (mm) — a mapped face
#: whose vertices do not land on an axis-aligned box within this bound is a
#: non-axis-aligned intermediate flange (out of the shipped emitter's scope, §4.3).
_AXIS_RECT_TOL_MM = 1e-6
#: Positive-area intersection floor for the self-overlap gate (mm). Two developed
#: flange regions overlapping by more than this in BOTH axes is a self-overlap
#: (touching edges — zero area — never count); tighter than the kernel linear tol.
_OVERLAP_TOL_MM = 1e-6


def _face_key(sig: PlanarFaceSignature) -> tuple[float, ...]:
    """A hashable in-run identity for a flat face (normal + centroid, rounded)."""
    return (
        round(sig.normal.x, _KEY_NORMAL_DP),
        round(sig.normal.y, _KEY_NORMAL_DP),
        round(sig.normal.z, _KEY_NORMAL_DP),
        round(sig.centroid.x, _KEY_CENTROID_DP),
        round(sig.centroid.y, _KEY_CENTROID_DP),
        round(sig.centroid.z, _KEY_CENTROID_DP),
    )


@dataclass(frozen=True)
class _ChainBend:
    """One resolved bend of the tree, oriented parent → child by provenance (§5)."""

    parent: FlangeFaceRecord
    child: FlangeFaceRecord
    axis_origin: Vector
    axis_dir: Vector
    radius_mm: float
    angle_rad: float
    allowance_mm: float
    k_factor: float
    width_mm: float


@dataclass(frozen=True)
class _Placement:
    """A flange's developed placement: an isometry from its own plane into the flat.

    ``phi(p) = R·[(p - o)·e1, (p - o)·e2] + t`` maps a 3D point on the flange's plane
    to its 2D developed coordinate. ``(e1, e2)`` is an orthonormal in-plane basis;
    ``R`` (2x2) + ``t`` places the flange into the flat plane. The base flange is
    placed at identity."""

    o: Vector
    e1: Vector
    e2: Vector
    r00: float
    r01: float
    r10: float
    r11: float
    tx: float
    ty: float

    def phi(self, p: Vector) -> Vec2:
        d = p - self.o
        a = d.dot(self.e1)
        b = d.dot(self.e2)
        return (
            self.r00 * a + self.r01 * b + self.tx,
            self.r10 * a + self.r11 * b + self.ty,
        )


def _perp(v: Vector, axis: Vector) -> Vector:
    """The component of *v* perpendicular to unit *axis*."""
    return v - axis * v.dot(axis)


def _project_to_plane(point: Vector, plane_pt: Vector, normal: Vector) -> Vector:
    """Orthogonal projection of *point* onto the plane through *plane_pt* with unit
    *normal* — the bend axis projects onto a flange plane to that flange's tangent
    contact line (the developable-surface tangent line, §9 #1)."""
    return point - normal * (point - plane_pt).dot(normal)


def _map_dir(pl: _Placement, v: Vector) -> Vec2:
    """A 3D in-plane direction expressed in *pl*'s developed frame (no translation)."""
    a = v.dot(pl.e1)
    b = v.dot(pl.e2)
    return (pl.r00 * a + pl.r01 * b, pl.r10 * a + pl.r11 * b)


def _unit2(v: Vec2) -> Vec2:
    length = math.hypot(v[0], v[1])
    return (v[0] / length, v[1] / length)


def _resolve_chain(
    body: BodyShape, bends: list[BendProvenance], thickness_mm: float
) -> list[_ChainBend]:
    """Resolve every bend by provenance and orient it parent → child (§5).

    The parent is the flanking flat matching the bend's recorded base-face signature;
    the child is the other flat. Construction provenance alone orients the tree — a
    depth-2 flange records its PARENT flange's signature, so no geometric guessing."""
    out: list[_ChainBend] = []
    for prov in bends:
        inner = resolve_cylindrical_face(body, prov.cyl_signature)
        rbf = resolve_bend_faces(body, inner)
        a, b = rbf.flanges
        if planar_signatures_match(a.signature, prov.base_face_signature):
            parent, child = a, b
        elif planar_signatures_match(b.signature, prov.base_face_signature):
            parent, child = b, a
        else:
            raise UnfoldStarError(
                "A bend's recorded base-face signature matches neither flanking flat; "
                "the bend cannot be oriented parent → child by provenance (§5)."
            )
        out.append(
            _ChainBend(
                parent=parent,
                child=child,
                axis_origin=Vector(*rbf.axis_origin),
                axis_dir=Vector(*rbf.axis_dir).normalized(),
                radius_mm=inner.radius,
                angle_rad=rbf.angle_rad,
                allowance_mm=bend_allowance(
                    rbf.angle_rad, inner.radius, prov.k_factor, thickness_mm
                ),
                k_factor=prov.k_factor,
                width_mm=child.width_mm,
            )
        )
    return out


def _find_root(chain: list[_ChainBend]) -> tuple[float, ...]:
    """The base-flange node: a bend parent that is never a bend child (the fixed
    tree root). Exactly one — else the bends are not a single rooted tree."""
    parents = {_face_key(b.parent.signature) for b in chain}
    children = {_face_key(b.child.signature) for b in chain}
    roots = parents - children
    if len(roots) != 1:
        raise UnfoldStarError(
            f"The bends do not form a single tree rooted at one base flange "
            f"(found {len(roots)} root candidates). The unfold handles a connected "
            "bend tree off one base (docs/design/sheet-metal.md §4.3)."
        )
    return next(iter(roots))


def _base_placement(root_rec: FlangeFaceRecord) -> _Placement:
    """Place the base flange at identity: its own plane is the developed plane.

    The in-plane basis is derived deterministically from the base normal (no face
    iteration order dependence), so the whole developed layout is reproducible."""
    n = Vector(*root_rec.normal).normalized()
    seed = Vector(1.0, 0.0, 0.0) if abs(n.X) < 0.9 else Vector(0.0, 1.0, 0.0)
    e1 = _perp(seed, n).normalized()
    e2 = n.cross(e1).normalized()
    return _Placement(
        o=Vector(*root_rec.centroid),
        e1=e1,
        e2=e2,
        r00=1.0,
        r01=0.0,
        r10=0.0,
        r11=1.0,
        tx=0.0,
        ty=0.0,
    )


def _place_child(parent_pl: _Placement, bend: _ChainBend) -> _Placement:
    """Compose the child's developed placement in the PARENT's flattened frame.

    The depth-≥2 crux: the child folds off a parent that is ITSELF already developed,
    so we express the bend's tangent line in the parent's 2D frame and place the child
    across a ``BA``-wide strip beyond it. Pure composition — the parent's map is
    applied to the shared tangent line, then offset by the bend allowance. No
    relaxation, no iteration. ``e2 = w_c`` is explicitly the child-interior direction,
    so its image ``wp2`` points OUTWARD across the strip regardless of the ``det=±1``
    handedness of the fold-axis image (the developed side is correct by construction;
    the overlap gate is the backstop for any residual misplacing)."""
    axis = bend.axis_dir
    o = bend.axis_origin
    p_n = Vector(*bend.parent.normal).normalized()
    c_n = Vector(*bend.child.normal).normalized()
    p_c = Vector(*bend.parent.centroid)
    c_c = Vector(*bend.child.centroid)

    # Tangent-contact lines: the bend axis projected onto each flange plane. cpP and
    # cpC share the bend's axial coordinate (projection removes only the normal
    # component, perpendicular to the axis), so they are corresponding points.
    cp_p = _project_to_plane(o, p_c, p_n)
    cp_c = _project_to_plane(o, c_c, c_n)

    # Fold-perpendicular directions (in-plane, perpendicular to the axis).
    w_c = _perp(c_c - cp_c, axis).normalized()  # bend → child interior
    w_p = _perp(cp_p - p_c, axis).normalized()  # parent interior → bend

    # Parent-frame images of the axis + parent fold-perpendicular direction.
    a2 = _unit2(_map_dir(parent_pl, axis))
    wp2 = _unit2(_map_dir(parent_pl, w_p))

    # Child placement: fold axis → a2; child interior → wp2 (continues outward across
    # the strip). Origin at the child tangent contact, offset one BA beyond the parent
    # tangent contact along wp2 (the developed bend strip).
    q_parent = parent_pl.phi(cp_p)
    tx = q_parent[0] + bend.allowance_mm * wp2[0]
    ty = q_parent[1] + bend.allowance_mm * wp2[1]
    return _Placement(
        o=cp_c,
        e1=axis,
        e2=w_c,
        r00=a2[0],
        r01=wp2[0],
        r10=a2[1],
        r11=wp2[1],
        tx=tx,
        ty=ty,
    )


def _flange_dev_rect(rec: FlangeFaceRecord, pl: _Placement) -> _Rect:
    """The flange's developed AXIS-ALIGNED rectangle (its mapped face vertices' bbox).

    Guards the shipped emitter's axis-aligned assumption: a mapped vertex not on the
    bbox corner grid means a non-axis-aligned flange (out of scope, §4.3) — a typed
    ``UnfoldStarError``, never a silently mislaid rectangle."""
    pts: list[Vec2] = []
    for v in rec.face.vertices():
        p = pl.phi(Vector(v.X, v.Y, v.Z))
        if not any(math.dist(p, q) <= _AXIS_RECT_TOL_MM for q in pts):
            pts.append(p)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    for p in pts:
        on_x = (
            abs(p[0] - min_x) <= _AXIS_RECT_TOL_MM
            or abs(p[0] - max_x) <= _AXIS_RECT_TOL_MM
        )
        on_y = (
            abs(p[1] - min_y) <= _AXIS_RECT_TOL_MM
            or abs(p[1] - max_y) <= _AXIS_RECT_TOL_MM
        )
        if not (on_x and on_y):
            raise UnfoldStarError(
                "A developed flange is not an axis-aligned rectangle in the flat "
                "frame (a non-axis-aligned intermediate flange). The shipped depth-≥2 "
                "emitter lays out axis-aligned rectangles only (§4.3 follow-on)."
            )
    return (min_x, min_y, max_x, max_y)


def _strip_dev_rect(
    parent_pl: _Placement, child_pl: _Placement, bend: _ChainBend
) -> _Rect:
    """The bend's developed BA-strip rectangle: the axis-aligned bbox of the parent
    and child tangent-contact lines (the strip bridges the two flange rectangles)."""
    axis = bend.axis_dir
    p_n = Vector(*bend.parent.normal).normalized()
    cp_p = _project_to_plane(bend.axis_origin, Vector(*bend.parent.centroid), p_n)
    cp_c = child_pl.o
    along = [
        (Vector(v.X, v.Y, v.Z) - cp_c).dot(axis) for v in bend.child.face.vertices()
    ]
    s0, s1 = min(along), max(along)
    corners: list[Vec2] = []
    for s in (s0, s1):
        corners.append(parent_pl.phi(cp_p + axis * s))
        corners.append(child_pl.phi(cp_c + axis * s))
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def _rects_overlap(a: _Rect, b: _Rect) -> bool:
    """True if two developed rectangles intersect with POSITIVE area (touching edges
    — zero area — never count) — the self-overlap predicate (§7)."""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    return ix > _OVERLAP_TOL_MM and iy > _OVERLAP_TOL_MM


def _cluster(values: list[float]) -> dict[float, float]:
    """Snap near-coincident coordinates (independently-computed flange vs. BA-strip
    interfaces coincide only to FP scale) to a shared representative, so the union
    grid has no spurious slivers. Real distinct coordinates (BA vs. leg lengths) are
    far apart (≫ tol); this only collapses the ≈1e-13 interface jitter."""
    out: dict[float, float] = {}
    reps: list[float] = []
    for v in sorted(values):
        if reps and v - reps[-1] <= _LOOP_TOL_MM:
            out[v] = reps[-1]
        else:
            reps.append(v)
            out[v] = v
    return out


def _snap_rects(rects: list[_Rect]) -> list[_Rect]:
    """Snap every rectangle's coordinates onto a shared clustered grid (per axis)."""
    xm = _cluster([r[i] for r in rects for i in (0, 2)])
    ym = _cluster([r[i] for r in rects for i in (1, 3)])
    return [(xm[r[0]], ym[r[1]], xm[r[2]], ym[r[3]]) for r in rects]


def _rectilinear_union_loop(rects: list[_Rect]) -> list[Vec2]:
    """The boundary of a union of axis-aligned rectangles as ONE closed CCW vertex
    loop (collinear runs merged). Raises ``UnfoldStarError`` if the boundary is not a
    single simple loop — a gap / hole / non-manifold junction (a partial-width flange
    would leave one), the depth-≥2 analogue of `_body_outline_is_closed_loop`."""
    xs = sorted({c for r in rects for c in (r[0], r[2])})
    ys = sorted({c for r in rects for c in (r[1], r[3])})

    def covered(cx: float, cy: float) -> bool:
        return any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in rects)

    inside: set[tuple[int, int]] = set()
    for i in range(len(xs) - 1):
        cx = (xs[i] + xs[i + 1]) / 2.0
        for j in range(len(ys) - 1):
            cy = (ys[j] + ys[j + 1]) / 2.0
            if covered(cx, cy):
                inside.add((i, j))

    # Directed boundary segments, oriented CCW (interior on the left) so head→tail
    # chaining is unambiguous. A cell side is boundary iff the neighbour across it is
    # outside the union.
    adj: dict[Vec2, Vec2] = {}
    for i, j in inside:
        x0, x1, y0, y1 = xs[i], xs[i + 1], ys[j], ys[j + 1]
        edges: list[tuple[Vec2, Vec2]] = []
        if (i, j - 1) not in inside:
            edges.append(((x0, y0), (x1, y0)))  # bottom, +x
        if (i, j + 1) not in inside:
            edges.append(((x1, y1), (x0, y1)))  # top, -x
        if (i - 1, j) not in inside:
            edges.append(((x0, y1), (x0, y0)))  # left, -y
        if (i + 1, j) not in inside:
            edges.append(((x1, y0), (x1, y1)))  # right, +y
        for s, e in edges:
            if s in adj:
                raise UnfoldStarError(
                    "The developed outline is non-manifold (a boundary vertex has two "
                    "outgoing edges); the flange layout does not tile a single blank."
                )
            adj[s] = e

    if not adj:
        raise UnfoldStarError("The developed outline is empty (no flange regions).")

    start = min(adj)
    loop: list[Vec2] = [start]
    cur = adj[start]
    while cur != start:
        loop.append(cur)
        nxt = adj.get(cur)
        if nxt is None:
            raise UnfoldStarError("The developed outline is not a closed loop (a gap).")
        cur = nxt
    if len(loop) != len(adj):
        raise UnfoldStarError(
            "The developed outline is more than one closed loop (a hole / detached "
            "region) — the flange layout does not tile a single blank (§4.3 / §7)."
        )
    return _merge_collinear(loop)


def _merge_collinear(loop: list[Vec2]) -> list[Vec2]:
    """Drop vertices interior to a straight run (the union grid emits unit edges)."""
    n = len(loop)
    out: list[Vec2] = []
    for k in range(n):
        a = loop[(k - 1) % n]
        b = loop[k]
        c = loop[(k + 1) % n]
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(cross) > _LOOP_TOL_MM:
            out.append(b)
    return out


def _unfold_bend_tree(
    body: BodyShape,
    bends: list[BendProvenance],
    thickness_mm: float,
    default_k_factor: float,
) -> FlatPattern:
    """Unfold a depth-≥2 bend TREE into a single-outline :class:`FlatPattern`.

    Resolves each bend by provenance, builds the bend tree, walks it from the base
    outward composing each flange's developed placement in its parent's already-flat
    frame (the spike's exact frame math), then assembles the ONE union outline and
    gates a self-overlapping development with a typed :class:`UnfoldOverlapError`.
    Byte-deterministic (§9 #4): every value flows from a deterministic OCCT
    measurement + closed-form allowance + a coordinate-sorted assembly.

    Raises:
        SubshapeUnresolvedError / SubshapeAmbiguousError: a bend signature no longer
            resolves against *body* (honest degradation, §5).
        UnfoldStarError: the bends are not a single rooted tree, or a developed
            flange / outline is not an axis-aligned single-loop layout (§4.3).
        UnfoldOverlapError: the development self-overlaps (needs corner relief, §7).
    """
    chain = _resolve_chain(body, bends, thickness_mm)
    root_key = _find_root(chain)
    root_rec = next(
        b.parent for b in chain if _face_key(b.parent.signature) == root_key
    )

    placements: dict[tuple[float, ...], _Placement] = {
        root_key: _base_placement(root_rec)
    }
    # BFS: place a bend's child once its parent is placed. Deterministic order —
    # bends sorted by a canonical geometric key, independent of the input order (§9).
    pending = sorted(
        chain,
        key=lambda b: (_face_key(b.parent.signature), _face_key(b.child.signature)),
    )
    placed_order: list[_ChainBend] = []
    guard = 0
    while pending:
        guard += 1
        if guard > len(chain) + 1:
            raise UnfoldStarError(
                "The bend tree is disconnected or cyclic — a child was never reached "
                "from the base flange (docs/design/sheet-metal.md §4.3)."
            )
        progressed = False
        for bend in list(pending):
            pk = _face_key(bend.parent.signature)
            ck = _face_key(bend.child.signature)
            if pk in placements and ck not in placements:
                placements[ck] = _place_child(placements[pk], bend)
                placed_order.append(bend)
                pending.remove(bend)
                progressed = True
        if not progressed:
            raise UnfoldStarError(
                "The bend tree is disconnected — a flange never chains back to the "
                "base (docs/design/sheet-metal.md §4.3)."
            )

    # Every flange record, keyed, base first.
    recs: dict[tuple[float, ...], FlangeFaceRecord] = {root_key: root_rec}
    for b in chain:
        recs[_face_key(b.child.signature)] = b.child

    # Developed flange rectangles (raw), and the SELF-OVERLAP gate (§7): two flange
    # regions colliding with positive area is a shape needing corner relief.
    flange_rects = {k: _flange_dev_rect(recs[k], placements[k]) for k in recs}
    ordered_keys = sorted(flange_rects)
    for i in range(len(ordered_keys)):
        for j in range(i + 1, len(ordered_keys)):
            if _rects_overlap(
                flange_rects[ordered_keys[i]], flange_rects[ordered_keys[j]]
            ):
                raise UnfoldOverlapError(
                    "The developed flat pattern self-overlaps: two flange regions "
                    "collide in 2D. This shape needs corner relief (§7, deferred); "
                    "the unfold refuses rather than emit an overlapping blank (§5)."
                )

    # BA-strip rectangles (one per bend), then snap flange+strip coords onto a shared
    # grid (independently-computed interfaces coincide only to FP scale).
    strip_rects = [
        _strip_dev_rect(
            placements[_face_key(b.parent.signature)],
            placements[_face_key(b.child.signature)],
            b,
        )
        for b in placed_order
    ]
    n_flange = len(ordered_keys)
    snapped = _snap_rects([flange_rects[k] for k in ordered_keys] + strip_rects)
    snapped_strips = snapped[n_flange:]

    loop = _rectilinear_union_loop(snapped)
    dx = min(p[0] for p in loop)
    dy = min(p[1] for p in loop)
    loop = [(p[0] - dx, p[1] - dy) for p in loop]

    all_x = [p[0] for p in loop]
    all_y = [p[1] for p in loop]

    outline: list[FlatEdge2D] = []
    n = len(loop)
    for i in range(n):
        x1, y1 = loop[i]
        x2, y2 = loop[(i + 1) % n]
        outline.append(FlatEdge2D(kind="line", x1=x1, y1=y1, x2=x2, y2=y2, role="body"))

    bend_lines: list[BendLine] = []
    for i, bend in enumerate(placed_order, start=1):
        sx0, sy0, sx1, sy1 = snapped_strips[i - 1]
        sx0, sx1 = sx0 - dx, sx1 - dx
        sy0, sy1 = sy0 - dy, sy1 - dy
        if (sx1 - sx0) <= (sy1 - sy0):  # strip thin in x → vertical fold centerline
            xm = (sx0 + sx1) / 2.0
            outline.append(
                FlatEdge2D(kind="line", x1=xm, y1=sy0, x2=xm, y2=sy1, role="bend")
            )
        else:  # strip thin in y → horizontal fold centerline
            ym = (sy0 + sy1) / 2.0
            outline.append(
                FlatEdge2D(kind="line", x1=sx0, y1=ym, x2=sx1, y2=ym, role="bend")
            )
        # Fold sense: child centroid on the +parent-normal side → "up".
        p_n = Vector(*bend.parent.normal).normalized()
        along_n = (Vector(*bend.child.centroid) - Vector(*bend.parent.centroid)).dot(
            p_n
        )
        bend_lines.append(
            BendLine(
                bend_id=f"bend-{i}",
                angle_deg=math.degrees(bend.angle_rad),
                radius_mm=bend.radius_mm,
                k_factor=bend.k_factor,
                allowance_mm=bend.allowance_mm,
                width_mm=bend.width_mm,
                direction="up" if along_n >= 0.0 else "down",
                flat_start_mm=0.0,
                flat_end_mm=bend.allowance_mm,
            )
        )

    outline.sort(key=lambda e: (e.role, e.x1, e.y1, e.x2, e.y2))
    bend_lines.sort(key=lambda bl: bl.bend_id)

    flat_area = sum(rec.area_mm2 for rec in recs.values()) + sum(
        b.allowance_mm * b.width_mm for b in chain
    )
    return FlatPattern(
        thickness_mm=thickness_mm,
        k_factor=default_k_factor,
        flat_length_mm=max(all_x) - min(all_x),
        flat_area_mm2=flat_area,
        bend_width_mm=max(all_y) - min(all_y),
        outline=tuple(outline),
        bends=tuple(bend_lines),
    )
